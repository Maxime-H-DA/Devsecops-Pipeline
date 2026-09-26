![Pipeline](https://github.com/Maxime-H-DA/devsecops-pipeline/actions/workflows/pipeline.yml/badge.svg)

# DevSecOps Pipeline

Plateforme DevSecOps complète, du commit jusqu'à la production : pipeline CI/CD sécurisé de 10 jobs, déploiement Kubernetes durci, infrastructure décrite en Terraform, secrets dans HashiCorp Vault et supervision Prometheus/Grafana.

Elle est appliquée à une API Flask en production (Render) et au jeu C++ dont l'API expose les données. L'objectif n'était pas l'application elle-même, mais de reproduire les pratiques d'une équipe DevOps en entreprise.

**En chiffres**
- 10 jobs CI en parallèle à chaque push et pull request, merge bloqué si un check échoue
- 45 tests unitaires, dont des tests d'attaque (contournement par faux en-tête d'adresse)
- 189 alertes Trivy triées à 26 CVE corrigeables, 7 problèmes de configuration HTTP (ZAP) et 7 mauvaises configurations Kubernetes (Checkov) corrigés
- 16 ressources Terraform : cluster, Kyverno, Vault, supervision et application
- 4 policies Kyverno en mode bloquant sur le namespace de l'application
- 1 incident réel détecté grâce à Grafana (pod lancé sans ses secrets), corrigé à 3 niveaux : injection, configuration, application

Le projet a grandi par étapes : d'abord le pipeline de sécurité, puis le déploiement sur Kubernetes, puis Vault pour les secrets, Terraform pour ne plus tout relancer à la main, et enfin la supervision. Chaque étape est partie d'un problème rencontré à l'étape d'avant.

## Avant même le push

Des hooks pre-commit tournent en local à chaque commit : Gitleaks, Bandit, Semgrep et Checkov (sur les manifests Kubernetes et sur le code Terraform) refont les mêmes vérifications qu'en CI mais avant que le code parte sur GitHub, avec en plus le contrôle du formatage Terraform et quelques hooks d'hygiène (espaces en fin de ligne, fichiers volumineux, YAML valide).

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
 |-- iac-scan-checkov : scan des manifests Kubernetes, du chart Helm et du code Terraform
 |-- kyverno-policy-test : teste les policies Kyverno contre les manifests
 `-- terraform-check : formatage et validation du code Terraform
```

Les 10 jobs tournent en parallèle, sans dépendance entre eux, à chaque push **et** à chaque pull request vers `main` : les scans passent avant le merge, pas après. Render déploie automatiquement de son côté ; `dast-api` se contente de réveiller puis scanner l'API déjà en ligne.

### Analyse du code avec Cppcheck

Le code C++ est scanné automatiquement pour détecter des bugs et problèmes avant même la compilation.

### Compilation dans Docker

Le jeu est compilé dans un environnement isolé, avec un encodage forcé en UTF-8 pour que ça tourne pareil sous Windows, Mac ou Linux. N'importe qui peut le lancer sans avoir à installer quoi que ce soit sur sa machine.

### Scan de sécurité avec Trivy

L'image Docker est analysée pour détecter des failles connues. Le premier scan a révélé une faille critique sur l'image de base utilisée pour compiler le jeu, d'où la migration vers Alpine Linux ; le scan suivant était propre.

### Analyse statique Python (Bandit + Semgrep)

L'API Flask est analysée avec deux outils complémentaires : Bandit détecte les vulnérabilités Python classiques, Semgrep applique les règles OWASP sur la sémantique du code.

### Test d'intrusion automatisé (OWASP ZAP)

À chaque push, ZAP teste l'API directement en production comme le ferait un attaquant externe. Le premier scan a remonté 7 problèmes de configuration HTTP : headers de sécurité manquants (nosniff, CSP, HSTS), pas de politique de cache sur les routes sensibles. Tous corrigés dans `app.py`.

### Sécurité supply chain (Syft + Cosign)

Chaque image poussée sur GitHub Container Registry génère un inventaire de ses dépendances (SBOM, format SPDX) et est signée en mode keyless via Sigstore : aucune clé privée à gérer, la signature s'appuie sur l'identité du workflow GitHub Actions et est publiée dans un registre de transparence public (Rekor).

### Scan d'infrastructure avec Checkov

Les manifests Kubernetes, le chart Helm et le code Terraform sont analysés à chaque push. Le premier scan a remonté 9 mauvaises configurations : UID trop bas (risque de collision avec un utilisateur hôte), secrets injectés en variables d'environnement au lieu de fichiers montés, système de fichiers du conteneur accessible en écriture, absence de politique réseau. 7 ont été corrigées dans les manifests et reproduites à l'identique dans le chart Helm ; les 2 restantes sont documentées et acceptées comme contraintes propres à Kind (pas de digest d'image disponible pour une image chargée localement, `imagePullPolicy` forcé à `IfNotPresent`).

### Test des policies Kyverno

Les 4 règles Kyverno (`policies/` : non-root obligatoire, pas de conteneur privilégié, limites CPU/mémoire obligatoires, pas de tag `latest`) sont rejouées contre les manifests via la CLI officielle, sans avoir besoin d'un cluster actif. Si une future modification des manifests casse une règle, la PR échoue avant le merge : pas besoin d'avoir son cluster Kind lancé pour le découvrir. Sur le cluster, ces règles bloquent réellement (mode Enforce) dans le namespace de l'application, et restent en observation (Audit) sur les composants tiers (Vault, Prometheus, Kubernetes lui-même), que les rapports d'Audit ont montrés non conformes.

### Validation du code Terraform

Terraform décrit toute l'infrastructure, c'est donc aussi la partie la plus sensible du repo. Chaque PR vérifie qu'il est correctement formaté (`terraform fmt -check`) et cohérent (`terraform validate`), avec la même version de Terraform qu'en local et les providers figés par le lock file. Rien n'est déployé : la CI n'a ni cluster ni state, elle contrôle uniquement le code.

### Tests unitaires (pytest)

L'API est couverte par 45 tests unitaires : authentification JWT, validation des données, gestion des erreurs, headers de sécurité, lecture des secrets depuis fichiers montés ou variables d'environnement, refus de démarrer si un secret manque, comptage des connexions refusées, limitation des tentatives de connexion (y compris une tentative de contournement par faux en-tête), et absence de page de métriques sur l'API publique.

## Résultats centralisés

Gitleaks, Bandit, Semgrep et Trivy publient tous leurs résultats dans l'onglet **Security > Code scanning** du repo, avec sévérité et ligne exacte : pas besoin de télécharger un rapport pour savoir ce qui a été trouvé. Les autres artefacts (SBOM, rapport ZAP complet, image de build Docker) restent téléchargeables depuis le run correspondant, puisqu'il ne s'agit pas d'alertes mais de documents de référence.

## Dépendances tenues à jour automatiquement

Dependabot surveille en continu les actions GitHub, les dépendances Python de l'API et les images Docker de base. Il ouvre une pull request à chaque nouvelle version disponible (avec un délai de 7 jours après la sortie, pour éviter une version tout juste publiée et pas encore éprouvée), qui passe par les mêmes 10 jobs avant de pouvoir être mergée.

## L'API du bestiaire

Une API Flask déployée sur [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com), avec une interface web pour consulter et modifier les monstres du jeu. La lecture est libre ; les modifications nécessitent une connexion avec identifiant et mot de passe.

Côté sécurité, l'API refuse de démarrer si l'un de ses secrets est absent, plutôt que de retomber sur des valeurs par défaut, et compare les identifiants en temps constant pour ne rien laisser deviner par le temps de réponse. Les tentatives de connexion sont limitées par adresse IP, de plus en plus strictement (5 par minute, 20 par heure, 50 par jour) ; une tentative de contournement par faux en-tête d'adresse a été testée en production.

## Déploiement

### Docker

Pour tester l'API en local sans impacter la version en ligne, utile pour tester des modifications de code avant de les déployer :

<details>
<summary>Commandes : lancer l'API avec Docker</summary>
 
```
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env -v rpg-data:/app/data rpg-api
```

</details>

L'API est alors accessible sur **http://localhost:5000**

### Kubernetes

L'API tourne aussi sur un cluster Kubernetes local avec Kind. Le conteneur s'exécute en non-root avec un système de fichiers en lecture seule, des ressources CPU et mémoire limitées, et des probes de santé qui surveillent que l'API répond. Les secrets sont injectés sous forme de fichiers montés plutôt qu'en variables d'environnement. Les 2 réplicas partagent un volume persistant (PVC) pour la base SQLite : sans ça, chaque pod aurait sa propre base isolée et les données auraient été incohérentes selon le pod qui répondait.

Les manifests de `k8s/` correspondent à la version avec Vault et se déploient avec Terraform (plus bas).

### Helm

C'est la première version du déploiement, avant Vault. Les secrets de l'API passent par un `Secret` Kubernetes créé depuis `.env`. En avançant, je me suis rendu compte qu'un Secret n'est qu'encodé en base64 : n'importe qui ayant accès au cluster peut le lire en une commande. C'est ce qui m'a amené à Vault (plus bas). Je garde cette version parce qu'elle reste la plus simple à lancer, et qu'elle montre d'où je suis parti.

Elle est packagée en chart Helm (`helm/rpg-api/`). Toutes les valeurs configurables (réplicas, ressources, UID, taille du volume...) sont centralisées dans `values.yaml` : changer l'environnement ne nécessite de modifier qu'un seul fichier, pas les manifests un par un. Le chart est scanné par Checkov en CI.

<details>
<summary>Commandes : déployer avec Helm (version sans Vault)</summary>
 
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

L'API est alors accessible sur **http://localhost:5000**

Note : avec Docker comme avec Helm, les modifications faites en local ne sont pas synchronisées avec la version en ligne.

### Terraform

Le cluster et tout ce qu'il contient sont décrits dans `terraform/` : cluster Kind, Kyverno et ses 4 policies, Vault, le déploiement de l'API et la supervision, avec des versions de charts figées. Deux `terraform apply` (le cluster d'abord, puis le reste) reconstruisent l'ensemble dans le bon ordre. Restent manuels, volontairement : l'ouverture de Vault et le dépôt des secrets, pour que rien de sensible ne passe par le state Terraform, et la construction de l'image, qui relève de la CI.

Les commandes complètes (Terraform, puis ouverture de Vault) sont dans la section suivante.

### Vault

Les identifiants applicatifs ne sont plus stockés dans un `Secret` Kubernetes, seulement encodé en base64 dans etcd et lisible en une commande : ils sont chiffrés dans Vault, et injectés au démarrage du pod par un sidecar. Chaque pod s'authentifie avec son propre ServiceAccount, reçoit un accès en lecture seule à durée limitée, sans jamais détenir de credential statique. Le token root est révoqué dès la configuration terminée.

<details>
<summary>Commandes : reconstruire tout l'environnement (Terraform, puis Vault)</summary>
 
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

L'API est alors accessible sur **http://localhost:5000**

### Prometheus et Grafana

Prometheus relève en continu l'état du cluster (CPU, mémoire, redémarrages, état des pods) et Grafana l'affiche en tableaux de bord. Installés par Terraform comme le reste, avec un mot de passe administrateur Grafana généré aléatoirement dans le cluster au lieu de la valeur par défaut du chart, connue de tous. La supervision porte sur le cluster local ; l'instance Render n'est pas supervisée, elle est protégée par la limitation des connexions côté API.

La supervision a servi dès le premier tableau de bord : un pod de l'API consommait moins de ressources que les autres, parce qu'il tournait **sans le sidecar Vault**, donc sans ses secrets. L'enquête a remonté trois défauts du même type, à trois niveaux :

- **Injection :** le webhook de l'injecteur Vault était en mode *fail-open*. Un pod créé avant que l'injecteur soit prêt passait sans sidecar, en silence. Passé en *fail-closed* (`failurePolicy: Fail`) : la création est refusée jusqu'à ce que l'injecteur réponde.
- **Configuration :** la policy Vault n'avait pas été chargée. Le token root, déjà révoqué, a été régénéré à partir de 3 clés de déverrouillage (`vault operator generate-root`) sans reconstruire Vault.
- **Application :** faute de secrets, l'API retombait sur des valeurs par défaut codées en dur (`admin` / `password`, clé JWT `changeme`), qu'aucun outil d'analyse statique n'avait signalées. Elle refuse désormais de démarrer si un secret manque.

L'API publie aussi ses propres mesures (requêtes, temps de réponse, connexions refusées) sur un port séparé, que seule la supervision peut joindre : la NetworkPolicy qui l'isole a été vérifiée par un test de blocage depuis un autre namespace. Une alerte se déclenche au-delà de 10 connexions refusées en 5 minutes : c'est la détection, en complément du blocage côté API.

<details>
<summary>Commandes : accéder à Grafana et Prometheus</summary>
 
```
$pw = kubectl get secret monitoring-grafana -n monitoring -o jsonpath="{.data.admin-password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```
 
</details>

Grafana est alors accessible sur **http://localhost:3000** (utilisateur `admin`), et Prometheus sur **http://localhost:9090** (alertes dans l'onglet *Alerts*). Chaque `port-forward` occupe son terminal.

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
- **Observabilité** : Prometheus, Grafana

## Projet source

Le code du jeu RPG : [projet-RPG-S6](https://github.com/Maxime-H-DA/projet-RPG-S6)
