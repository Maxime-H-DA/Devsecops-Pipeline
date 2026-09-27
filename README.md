![Pipeline](https://github.com/Maxime-H-DA/devsecops-pipeline/actions/workflows/pipeline.yml/badge.svg)

# DevSecOps Pipeline

Plateforme DevSecOps complète, du commit jusqu'à la production : pipeline CI/CD sécurisé, déploiement Kubernetes durci, infrastructure décrite en Terraform, secrets dans HashiCorp Vault et supervision Prometheus/Grafana.

Le tout est appliqué à une API Flask en production sur [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com), qui expose les monstres d'un jeu RPG en C++. L'objectif n'était pas l'application elle-même, mais de reproduire les pratiques d'une équipe DevOps en entreprise.

**En bref**
- 10 jobs CI à chaque push et pull request, dont 8 bloquants : le merge est impossible si l'un échoue
- 45 tests unitaires, dont des tests d'attaque
- 189 alertes Trivy triées, failles de configuration HTTP (ZAP) et Kubernetes (Checkov) corrigées
- 16 ressources Terraform pour reconstruire tout l'environnement
- 4 policies Kyverno en mode bloquant
- Secrets chiffrés dans Vault, jamais stockés en clair dans le cluster

## Pipeline CI/CD

```
push / pull request -> main
 |
 |-- en parallèle, bloquants :
 |    |-- analyse-code : Gitleaks + Cppcheck (code C++)
 |    |-- scan-jeu : Build Docker (jeu) + Trivy
 |    |-- scan-api : Build Docker (API) + Trivy
 |    |-- sast-api : Bandit + Semgrep
 |    |-- tests-api : pytest
 |    |-- iac-scan-checkov : manifests Kubernetes, chart Helm et Terraform
 |    |-- kyverno-policy-test : policies Kyverno rejouées contre les manifests
 |    `-- terraform-check : formatage et validation du code Terraform
 |
 |-- en parallèle, non bloquant :
 |    `-- dast-api : OWASP ZAP sur l'API en ligne (Render)
 |
 `-- après les 8 jobs bloquants, sur main uniquement :
      `-- supply-chain-api : publication de l'image, SBOM (Syft) + signature (Cosign)
```

Les scans passent avant le merge, pas après, et seule une image validée par tous les contrôles est publiée et signée. Des hooks pre-commit refont l'essentiel en local avant même le push, les résultats remontent dans l'onglet **Security > Code scanning**, et Dependabot garde les dépendances à jour en passant par les mêmes contrôles.

## Déploiement

### Docker

La façon la plus rapide de lancer l'API en local.

<details>
<summary>Commandes</summary>

```
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env -v rpg-data:/app/data rpg-api
```

</details>

L'API est accessible sur **http://localhost:5000**

### Helm

Première version du déploiement Kubernetes (Kind), avant Vault : conteneur non-root, système de fichiers en lecture seule, ressources limitées, probes de santé et NetworkPolicy. Les secrets passent encore par un `Secret` Kubernetes.

<details>
<summary>Commandes</summary>

```
kind create cluster --config k8s/kind-config.yaml
docker build -t rpg-api:local -f rpg-api/Dockerfile .
kind load docker-image rpg-api:local --name rpg-pipeline
helm install rpg-api helm/rpg-api --namespace rpg-pipeline --create-namespace
kubectl create secret generic rpg-api-secret --namespace rpg-pipeline --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

</details>

L'API est accessible sur **http://localhost:5000**

### Terraform et Vault

Version complète : Terraform reconstruit le cluster, Kyverno, Vault, l'application et la supervision. Les secrets sont chiffrés dans Vault et injectés au démarrage du pod par un sidecar ; chaque pod s'authentifie avec son propre ServiceAccount, en lecture seule et à durée limitée.

<details>
<summary>Commandes</summary>

```
cd terraform
terraform init
terraform apply "-target=kind_cluster.rpg"
terraform apply
cd ..

docker build -t rpg-api:local -f rpg-api/Dockerfile .
kind load docker-image rpg-api:local --name rpg-pipeline

$init = kubectl exec -n vault vault-0 -- vault operator init -key-shares=5 -key-threshold=3 -format=json | ConvertFrom-Json
$keys = $init.unseal_keys_b64
$token = $init.root_token

kubectl exec -n vault vault-0 -- vault operator unseal $keys[0]
kubectl exec -n vault vault-0 -- vault operator unseal $keys[1]
kubectl exec -n vault vault-0 -- vault operator unseal $keys[2]
kubectl exec -n vault vault-0 -- vault login -no-print $token

kubectl exec -n vault vault-0 -- vault auth enable kubernetes
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443"
kubectl exec -n vault vault-0 -- vault secrets enable -path=secret kv-v2

Get-Content vault/policies/rpg-api-policy.hcl -Raw | kubectl exec -i -n vault vault-0 -- vault policy write rpg-api -
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/rpg-api bound_service_account_names=rpg-api bound_service_account_namespaces=rpg-pipeline policies=rpg-api ttl=1h

kubectl exec -n vault vault-0 -- mkdir -p /vault/audit
kubectl exec -n vault vault-0 -- chmod u+x /vault/audit
kubectl exec -n vault vault-0 -- vault audit enable file file_path=/vault/audit/audit.log

.\vault\seed-secrets.ps1
kubectl exec -n vault vault-0 -- vault token revoke -self

kubectl rollout restart deployment/rpg-api -n rpg-pipeline
kubectl rollout status deployment/rpg-api -n rpg-pipeline --timeout=180s

# Clés de déverrouillage : à conserver hors du repo, nécessaires pour rouvrir Vault
$keys

kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

</details>

L'API est accessible sur **http://localhost:5000**

## Supervision

Prometheus relève l'état du cluster et les mesures de l'API, Grafana les affiche en tableaux de bord. Une alerte se déclenche au-delà de 10 connexions refusées en 5 minutes.

<details>
<summary>Commandes</summary>

```
$pw = kubectl get secret monitoring-grafana -n monitoring -o jsonpath="{.data.admin-password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

</details>

Grafana est accessible sur **http://localhost:3000** (utilisateur `admin`), Prometheus sur **http://localhost:9090**. Chaque `port-forward` occupe son terminal.

## Synchronisation avec le jeu

```
py play.py
```

Le script récupère les monstres depuis l'API en ligne et met à jour `monsters.csv` avant de lancer le jeu.

## Outils utilisés

- **CI/CD & infrastructure** : GitHub Actions, Docker, Kubernetes (Kind), Helm, Terraform, Alpine Linux, Dependabot
- **Sécurité** : Gitleaks, Trivy, Bandit, Semgrep, OWASP ZAP, Cppcheck, Checkov, Kyverno, Syft, Cosign, HashiCorp Vault
- **Backend & tests** : Flask, SQLite, JWT, pytest
- **Observabilité** : Prometheus, Grafana

## Projet source

Le code du jeu RPG (projet S6) : [Alterdune](https://github.com/Maxime-H-DA/Alterdune)
