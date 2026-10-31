[![CI/CD](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml)

# Pipeline DevSecOps

Un chemin sécurisé du commit à la production pour une API Flask qui sert les monstres d'un jeu RPG en C++, en ligne sur [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com). L'application est volontairement simple : l'intérêt est la plateforme qui l'entoure, construite comme le ferait une équipe DevOps en entreprise.

## Points clés

- **CI/CD** : 12 jobs GitHub Actions à chaque push et pull request, dont 10 obligatoires pour merger. L'image n'est publiée et signée que si toutes les vérifications passent.
- **Sécurité des conteneurs** : l'image de l'API passe de 165 à 2 CVE Trivy grâce à une Docker Hardened Image (sans shell, sans gestionnaire de paquets). Elle est construite une seule fois, scannée avec Trivy, attaquée avec OWASP ZAP, puis signée avec Cosign avec son SBOM.
- **Chaîne d'approvisionnement** : Render et le cluster n'exécutent que le digest signé, et Kyverno bloque toute image non signée de l'API.
- **Infrastructure as code** : 19 ressources Terraform reconstruisent la plateforme Kubernetes. Argo CD déploie l'application depuis Git et annule toute modification manuelle.
- **Secrets** : chiffrés dans HashiCorp Vault et injectés au démarrage, jamais stockés dans Git ni dans des Secrets Kubernetes. L'API a un accès en lecture seule et limité dans le temps, et ses pods ne peuvent joindre que le DNS et Vault.
- **Détection à l'exécution** : Falco signale tout processus inattendu dans le conteneur de l'API ou toute lecture tardive de ses secrets.
- **Tests** : 60 tests unitaires (98 % de couverture) incluant des scénarios d'attaque, plus des tests pour les politiques Kyverno et les alertes Prometheus.
- **Maintenance** : 189 alertes Trivy triées sur l'image du jeu, findings ZAP et Checkov corrigés. Dependabot et Renovate maintiennent les dépendances à jour en passant par les mêmes vérifications.

## Pipeline CI/CD

```
push / pull request -> main
 |
 |-- étape 1, en parallèle :
 |    |-- analyse-code: Gitleaks + Cppcheck (code C++)
 |    |-- scan-jeu: build Docker (jeu) + Trivy
 |    |-- sast-api: Bandit + Semgrep
 |    |-- tests-api: pytest, couverture minimum 95 %
 |    |-- iac-scan-checkov: manifests Kubernetes et Terraform
 |    |-- kyverno-policy-test: tests des politiques Kyverno + tests unitaires des alertes Prometheus
 |    |-- terraform-check: formatage et validation du code Terraform
 |    `-- build-api: build Docker de l'API, fait une seule fois
 |
 |-- étape 2, sur l'image construite à l'étape 1 :
 |    |-- scan-api: Trivy
 |    `-- dast-api-local: smoke test + OWASP ZAP contre le conteneur en cours d'exécution
 |
 |-- étape 3, sur main uniquement, si tout est passé :
 |    `-- supply-chain-api: publication, SBOM (Syft), signature et attestation du SBOM (Cosign), déploiement sur Render
 |
 `-- étape 4, sur main uniquement, après le déploiement :
      `-- dast-api: attend que Render serve exactement ce commit (/version), puis OWASP ZAP contre la production, en tant que surveillance
```

Les findings sont publiés dans l'onglet **Security > Code scanning**, et des hooks pre-commit exécutent Gitleaks, Bandit, Semgrep, Checkov et le formatage Terraform avant chaque commit.

## Déploiement

Les deux méthodes nécessitent Docker et un fichier `.env` à la racine du repo avec `API_SECRET_KEY`, `ADMIN_USERNAME` et `ADMIN_PASSWORD`. Les commandes sont pour PowerShell (Windows).

### Docker

La façon la plus rapide de lancer l'API en local. L'image de base provient de Docker Hardened Images, donc `docker login dhi.io` nécessite un compte Docker.

<details>
<summary>Commandes</summary>

```
docker login dhi.io
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env rpg-api
```

</details>

L'API est disponible sur **http://localhost:5000**

### Terraform et Vault

La plateforme complète : Terraform construit un cluster Kind avec Kyverno, Vault, le monitoring, Falco et Argo CD, puis Argo CD déploie l'API. Nécessite aussi Terraform et kubectl.

<details>
<summary>Commandes</summary>

```
cd terraform
terraform init
terraform apply "-target=kind_cluster.rpg"
terraform apply
cd ..

.\vault\init-vault.ps1

kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

`init-vault.ps1` initialise et configure Vault, charge les secrets depuis `.env`, puis révoque le root token. Les clés d'unseal sont chiffrées avec Windows DPAPI et stockées dans `.vault-keys/`, ignoré par Git.

</details>

<details>
<summary>Après un redémarrage de Docker ou du PC</summary>

```
.\vault\unseal-vault.ps1
```

Le script redémarre le cluster, unseal Vault et redémarre l'API.

</details>

L'API est disponible sur **http://localhost:5000**

## GitOps

Argo CD déploie `k8s/` depuis la branche `main` et maintient le cluster identique à Git. Argo CD Image Updater déploie automatiquement chaque nouvelle image signée.

<details>
<summary>Commandes</summary>

```
$pw = kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n argocd svc/argocd-server 8080:443
```

</details>

Argo CD est disponible sur **https://localhost:8080** (utilisateur `admin`, certificat auto-signé).

## Monitoring

Prometheus collecte les métriques du cluster et de l'API, et Grafana les affiche. Des alertes se déclenchent au-delà de 10 connexions refusées en 5 minutes, sur les détections Falco, et quand Falco devient silencieux.

<details>
<summary>Commandes</summary>

```
$pw = kubectl get secret monitoring-grafana -n monitoring -o jsonpath="{.data.admin-password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

</details>

Grafana est disponible sur **http://localhost:3000** (utilisateur `admin`), Prometheus sur **http://localhost:9090**. Chaque `port-forward` occupe son propre terminal.

## Synchronisation du jeu

```
py play.py
```

Le script récupère les monstres depuis l'API en ligne et met à jour le fichier `monsters.csv` du jeu. Code du jeu (projet S6) : [Alterdune](https://github.com/Maxime-H-DA/Alterdune)


## Outils utilisés

- **CI/CD & infrastructure** : GitHub Actions, Docker, Docker Hardened Images, Kubernetes (Kind), Helm, Terraform, Argo CD, Alpine Linux, Dependabot, Renovate
- **Sécurité** : Gitleaks, Trivy, Bandit, Semgrep, OWASP ZAP, Cppcheck, Checkov, Kyverno, Falco, Syft, Cosign, HashiCorp Vault
- **Backend & tests** : Flask, Gunicorn, SQLite, JWT, pytest
- **Observabilité** : Prometheus, Grafana
