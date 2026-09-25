![Pipeline](https://github.com/Maxime-H-DA/rpg-pipeline/actions/workflows/pipeline.yml/badge.svg)

# Pipeline du RPG Alterdune

Pipeline CI/CD sécurisé autour de mon projet RPG en C++ : vérification automatique du code, compilation dans un environnement isolé, et détection de failles de sécurité à chaque modification (SAST, DAST, scan de conteneurs, sécurité supply chain, déploiement Kubernetes).

L'idée était de prendre un vrai projet et de lui appliquer des pratiques qu'on retrouve en entreprise.

## Avant même le push

Des hooks pre-commit tournent en local à chaque commit : Gitleaks, Bandit, Semgrep et Checkov refont les mêmes vérifications qu'en CI mais avant que le code parte sur GitHub, en plus de quelques hooks d'hygiène (espaces en fin de ligne, fichiers volumineux, YAML valide).

## Ce qui se passe à chaque push et à chaque pull request

```
push (main) / pull request -> main
 |-- analyse-code : Gitleaks + Cppcheck (code C++)
 |-- scan-jeu : Build Docker (jeu) + Trivy
 |-- scan-api : Build Docker (API) + Trivy
 |-- sast-api : Bandit + Semgrep
 |-- tests-api : pytest
 |-- dast-api : OWASP ZAP sur l'API déjà en ligne (Render)
 |-- supply-chain-api : SBOM (Syft) + signature de l'image (Cosign)
 |-- iac-scan-checkov : scan des manifests Kubernetes et du chart Helm
 `-- kyverno-policy-test : teste les policies Kyverno contre les manifests
```

Les 9 jobs tournent en parallèle, sans dépendance entre eux, à chaque push **et** à chaque pull request vers `main` : les scans passent avant le merge, pas après. Render déploie automatiquement de son côté ; `dast-api` se contente de réveiller puis scanner l'API déjà en ligne.

#### Analyse du code avec Cppcheck

Le code C++ est scanné automatiquement pour détecter des bugs et problèmes avant même la compilation.

#### Compilation dans Docker

Le jeu est compilé dans un environnement isolé, avec un encodage forcé en UTF-8 pour que ça tourne pareil sous Windows, Mac ou Linux. N'importe qui peut le lancer sans avoir à installer quoi que ce soit sur sa machine.

#### Scan de sécurité avec Trivy

L'image Docker est analysée pour détecter des failles connues. Le premier scan a révélé une faille critique sur l'image de base utilisée pour compiler le jeu, d'où la migration vers Alpine Linux ; le scan suivant était propre.

#### Analyse statique Python (Bandit + Semgrep)

L'API Flask est analysée avec deux outils complémentaires : Bandit détecte les vulnérabilités Python classiques, Semgrep applique les règles OWASP sur la sémantique du code.

#### Test d'intrusion automatisé (OWASP ZAP)

À chaque push, ZAP teste l'API directement en production comme le ferait un attaquant externe. Le premier scan a remonté 7 problèmes de configuration HTTP : headers de sécurité manquants (nosniff, CSP, HSTS), pas de politique de cache sur les routes sensibles. Tous corrigés dans `app.py`.

#### Sécurité supply chain (Syft + Cosign)

Chaque image poussée sur GitHub Container Registry génère un inventaire de ses dépendances (SBOM, format SPDX) et est signée en mode keyless via Sigstore : aucune clé privée à gérer, la signature s'appuie sur l'identité du workflow GitHub Actions et est publiée dans un registre de transparence public (Rekor).

#### Scan d'infrastructure avec Checkov

Les manifests Kubernetes et le chart Helm sont analysés à chaque push. Le premier scan a remonté 9 mauvaises configurations : UID trop bas (risque de collision avec un utilisateur hôte), secrets injectés en variables d'environnement au lieu de fichiers montés, système de fichiers du conteneur accessible en écriture, absence de politique réseau. 7 ont été corrigées dans les manifests et reproduites à l'identique dans le chart Helm ; les 2 restantes sont documentées et acceptées comme contraintes propres à Kind (pas de digest d'image disponible pour une image chargée localement, `imagePullPolicy` forcé à `IfNotPresent`).

#### Test des policies Kyverno

Les 4 règles Kyverno (voir section Kubernetes) sont rejouées contre les manifests via la CLI officielle, sans avoir besoin d'un cluster actif. Si une future modification des manifests casse une règle, la PR échoue avant le merge : pas besoin d'avoir son cluster Kind lancé pour le découvrir.

#### Tests unitaires (pytest)

L'API est couverte par 36 tests unitaires : authentification JWT, validation des données, gestion des erreurs, headers de sécurité, lecture des secrets depuis fichiers montés ou variables d'environnement. Les tests tournent sur une base SQLite isolée pour ne pas polluer les données de production.

## Résultats centralisés

Gitleaks, Bandit, Semgrep et Trivy publient tous leurs résultats dans l'onglet **Security > Code scanning** du repo, avec sévérité et ligne exacte : pas besoin de télécharger un rapport pour savoir ce qui a été trouvé. Les autres artefacts (SBOM, rapport ZAP complet, image de build Docker) restent téléchargeables depuis le run correspondant, puisqu'il ne s'agit pas d'alertes mais de documents de référence.

## Dépendances tenues à jour automatiquement

Dependabot surveille en continu les actions GitHub, les dépendances Python de l'API et les images Docker de base. Il ouvre une pull request à chaque nouvelle version disponible (avec un délai de 7 jours après la sortie, pour éviter une version tout juste publiée et pas encore éprouvée), qui passe par les mêmes 9 jobs avant de pouvoir être mergée.

## L'API du bestiaire

Une API Flask déployée sur [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com) qui expose les données des monstres du jeu. La lecture est libre, les modifications nécessitent une connexion avec identifiant et mot de passe.

### Docker

Pour tester l'API en local sans impacter la version en ligne, utile pour tester des modifications de code avant de les déployer :

```
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env -v rpg-data:/app/data rpg-api
```

L'API est alors accessible sur **http://localhost:5000**

### Kubernetes

L'API tourne aussi sur un cluster Kubernetes local avec Kind. Le conteneur s'exécute en non-root avec un système de fichiers en lecture seule, des ressources CPU et mémoire limitées, et des probes de santé qui surveillent que l'API répond. Les secrets sont injectés sous forme de fichiers montés plutôt qu'en variables d'environnement. Les 2 réplicas partagent un volume persistant (PVC) pour la base SQLite : sans ça, chaque pod aurait sa propre base isolée et les données auraient été incohérentes selon le pod qui répondait.

```
kind create cluster --config k8s/kind-config.yaml
docker build -t rpg-api:local -f rpg-api/Dockerfile .
kind load docker-image rpg-api:local --name rpg-pipeline
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/05-pvc.yaml
kubectl create secret generic rpg-api-secret --namespace rpg-pipeline --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/02-deployment.yaml
kubectl apply -f k8s/03-service.yaml
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

L'API est alors accessible sur **http://localhost:5000**

Note : avec les deux méthodes, les modifications faites en local ne sont pas synchronisées avec la version en ligne.

### Helm

Le même déploiement existe aussi packagé en chart Helm (`helm/rpg-api/`). Toutes les valeurs configurables (réplicas, ressources, UID, taille du volume...) sont centralisées dans `values.yaml` : changer l'environnement ne nécessite de modifier qu'un seul fichier, pas les manifests un par un. Le chart est scanné par Checkov en CI et produit le même résultat que les manifests bruts.

```
kind create cluster --config k8s/kind-config.yaml
docker build -t rpg-api:local -f rpg-api/Dockerfile .
kind load docker-image rpg-api:local --name rpg-pipeline
helm install rpg-api helm/rpg-api --namespace rpg-pipeline --create-namespace
kubectl create secret generic rpg-api-secret --namespace rpg-pipeline --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

L'API est alors accessible sur **http://localhost:5000**

### Terraform

Le cluster et tout ce qu'il contient sont décrits dans `terraform/` : cluster Kind, Kyverno et ses 4 policies, Vault et le déploiement de l'API, avec des versions de charts figées. Deux `terraform apply` (le cluster d'abord, puis le reste) reconstruisent l'ensemble dans le bon ordre. Seule l'ouverture de Vault reste manuelle, pour que ses clés ne passent jamais par le state Terraform.

### Gestion des secrets avec Vault

Les identifiants applicatifs ne sont plus stockés dans un `Secret` Kubernetes, seulement encodé en base64 dans etcd et lisible en une commande : ils sont chiffrés dans Vault, et injectés au démarrage du pod par un sidecar. Chaque pod s'authentifie avec son propre ServiceAccount, reçoit un accès en lecture seule à durée limitée, sans jamais détenir de credential statique. Le token root est révoqué dès la configuration terminée.

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
$keys

kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

L'API est alors accessible sur **http://localhost:5000**

## Synchronisation avec le jeu

Pour jouer avec les données en ligne plutôt que les données locales :

```
py play.py
```

`monsters.csv` est la copie locale des monstres du jeu C++, régénérée à chaque lancement. Le script récupère les monstres depuis l'API et met à jour ce fichier avant que le jeu démarre.

## Outils utilisés

- **CI/CD & infrastructure** : GitHub Actions, Docker, Kubernetes (Kind), Helm, Terraform, Alpine Linux, Dependabot
- **Sécurité** : Gitleaks, Trivy, Bandit, Semgrep, OWASP ZAP, Cppcheck, Checkov, Kyverno, Syft, Cosign, HashiCorp Vault
- **Backend & tests** : Flask, SQLite, JWT, pytest

## Projet source

Le code du jeu RPG : [projet-RPG-S6](https://github.com/Maxime-H-DA/projet-RPG-S6)
