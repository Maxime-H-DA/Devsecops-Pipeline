[![CI/CD](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml)

# DevSecOps Pipeline

A secure path from commit to production for a Flask API that serves the monsters of a C++ RPG game, live at [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com). The application is deliberately simple: the point is the platform around it, built the way an enterprise DevOps team would.

## Highlights

- **CI/CD**: 12 GitHub Actions jobs on every push and pull request, 10 of them required to merge. The image is published and signed only if all checks pass.
- **Container security**: the API image goes from 165 to 2 Trivy CVEs thanks to a Docker Hardened Image (no shell, no package manager). It is built once, scanned with Trivy, attacked with OWASP ZAP, then signed with Cosign along with its SBOM.
- **Supply chain**: Render and the cluster run only the signed digest, and Kyverno blocks any unsigned image of the API.
- **Infrastructure as code**: 19 Terraform resources rebuild the Kubernetes platform. Argo CD deploys the application from Git and reverts any manual change.
- **Secrets**: encrypted in HashiCorp Vault and injected at startup, never stored in Git or in Kubernetes Secrets. The API has read-only, time-limited access, and its pods can only reach DNS and Vault.
- **Runtime detection**: Falco flags any unexpected process in the API container or late read of its secrets.
- **Tests**: 60 unit tests (98% coverage) including attack scenarios, plus tests for the Kyverno policies and the Prometheus alerts.
- **Maintenance**: 189 Trivy alerts triaged on the game image, ZAP and Checkov findings fixed. Dependabot and Renovate keep dependencies up to date through the same checks.

## CI/CD Pipeline

```
push / pull request -> main
 |
 |-- step 1, in parallel:
 |    |-- analyse-code: Gitleaks + Cppcheck (C++ code)
 |    |-- scan-jeu: Docker build (game) + Trivy
 |    |-- sast-api: Bandit + Semgrep
 |    |-- tests-api: pytest, minimum 95% coverage
 |    |-- iac-scan-checkov: Kubernetes manifests and Terraform
 |    |-- kyverno-policy-test: Kyverno policy tests + Prometheus alert unit tests
 |    |-- terraform-check: Terraform code formatting and validation
 |    `-- build-api: Docker build of the API, done once
 |
 |-- step 2, on the image built in step 1:
 |    |-- scan-api: Trivy
 |    `-- dast-api-local: smoke test + OWASP ZAP against the running container
 |
 |-- step 3, on main only, if everything passed:
 |    `-- supply-chain-api: publishing, SBOM (Syft), signing and SBOM attestation (Cosign), deployment to Render
 |
 `-- step 4, on main only, after the deployment:
      `-- dast-api: waits until Render serves this exact commit (/version), then OWASP ZAP against production, as monitoring
```

Findings are published in the **Security > Code scanning** tab, and pre-commit hooks run Gitleaks, Bandit, Semgrep, Checkov and Terraform formatting before each commit.

## Deployment

Both methods need Docker and a `.env` file at the root of the repo with `API_SECRET_KEY`, `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Commands are for PowerShell (Windows).

### Docker

The quickest way to run the API locally. The base image comes from Docker Hardened Images, so `docker login dhi.io` needs a Docker account.

<details>
<summary>Commands</summary>

```
docker login dhi.io
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env rpg-api
```

</details>

The API is available at **http://localhost:5000**

### Terraform and Vault

The full platform: Terraform builds a Kind cluster with Kyverno, Vault, monitoring, Falco and Argo CD, then Argo CD deploys the API. Also requires Terraform and kubectl.

<details>
<summary>Commands</summary>

```
cd terraform
terraform init
terraform apply "-target=kind_cluster.rpg"
terraform apply
cd ..

.\vault\init-vault.ps1

kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

`init-vault.ps1` initializes and configures Vault, loads the secrets from `.env`, then revokes the root token. The unseal keys are encrypted with Windows DPAPI and stored in `.vault-keys/`, ignored by Git.

</details>

<details>
<summary>After a Docker or PC restart</summary>

```
.\vault\unseal-vault.ps1
```

The script restarts the cluster, unseals Vault and restarts the API.

</details>

The API is available at **http://localhost:5000**

## GitOps

Argo CD deploys `k8s/` from the `main` branch and keeps the cluster identical to Git. Argo CD Image Updater deploys each new signed image automatically.

<details>
<summary>Commands</summary>

```
$pw = kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n argocd svc/argocd-server 8080:443
```

</details>

Argo CD is available at **https://localhost:8080** (user `admin`, self-signed certificate).

## Monitoring

Prometheus collects cluster and API metrics, and Grafana displays them. Alerts fire on more than 10 rejected logins within 5 minutes, on Falco detections, and when Falco goes silent.

<details>
<summary>Commands</summary>

```
$pw = kubectl get secret monitoring-grafana -n monitoring -o jsonpath="{.data.admin-password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($pw))
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

</details>

Grafana is available at **http://localhost:3000** (user `admin`), Prometheus at **http://localhost:9090**. Each `port-forward` takes up its own terminal.

## Game Sync

```
py play.py
```

The script fetches the monsters from the live API and updates the game's `monsters.csv`. Game code (S6 project): [Alterdune](https://github.com/Maxime-H-DA/Alterdune)


## Tools Used

- **CI/CD & infrastructure**: GitHub Actions, Docker, Docker Hardened Images, Kubernetes (Kind), Helm, Terraform, Argo CD, Alpine Linux, Dependabot, Renovate
- **Security**: Gitleaks, Trivy, Bandit, Semgrep, OWASP ZAP, Cppcheck, Checkov, Kyverno, Falco, Syft, Cosign, HashiCorp Vault
- **Backend & testing**: Flask, Gunicorn, SQLite, JWT, pytest
- **Observability**: Prometheus, Grafana
