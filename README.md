[![CI/CD](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Maxime-H-DA/Devsecops-Pipeline/actions/workflows/pipeline.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Maxime-H-DA/Devsecops-Pipeline/badge)](https://scorecard.dev/viewer/?uri=github.com/Maxime-H-DA/Devsecops-Pipeline)

# DevSecOps Pipeline

End-to-end DevSecOps platform, from commit to production: secure CI/CD pipeline, hardened Kubernetes deployment, infrastructure defined in Terraform, secrets in HashiCorp Vault, and monitoring with Prometheus/Grafana.

All of it is applied to a Flask API running in production at [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com), which serves the monsters of a C++ RPG game. The goal wasn't the application itself, but to reproduce the practices of an enterprise DevOps team.

**At a glance**
- 12 CI jobs on every push and pull request, 10 of them required to merge; the image is published and signed only if all checks pass
- The Docker image is built once on a hardened base (no shell, no package manager, 3x fewer vulnerabilities), scanned (Trivy), attacked (OWASP ZAP), then signed (Cosign)
- Only the image signed by the pipeline runs: Render deploys its exact digest, and the cluster picks up each new signed image automatically, verified by Kyverno
- Runtime detection with Falco: an unexpected process in the API container or a late read of its secrets fires an alert
- 60 unit tests (98% coverage) including attack tests, plus tests for the Kyverno policies and the Prometheus alerts
- 189 Trivy alerts triaged, HTTP (ZAP) and Kubernetes (Checkov) misconfigurations fixed
- 18 Terraform resources rebuild the platform; Argo CD deploys the application from Git
- Argo CD keeps the cluster identical to Git: manual changes and deletions are reverted automatically
- Secrets encrypted in Vault, never stored in Kubernetes Secrets or in Git

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
 `-- step 3, on main only, if everything passed:
      `-- supply-chain-api: publishing, SBOM (Syft), signing and SBOM attestation (Cosign), deployment to Render

On main, after the deployment, dast-api waits until Render serves this exact commit (/version), then scans it with OWASP ZAP, as monitoring.
```

Scans run before the merge, not after, and Render no longer builds anything: it only deploys the image the pipeline has tested and signed. Pre-commit hooks rerun most of these checks locally before the push even happens, results show up in the **Security > Code scanning** tab, and Dependabot keeps dependencies up to date by going through the same checks.

## Deployment

Both methods need a `.env` file at the root of the repo with `API_SECRET_KEY`, `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Commands are for PowerShell (Windows).

### Docker

The quickest way to run the API locally.

<details>
<summary>Commands</summary>

```
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env rpg-api
```

</details>

The API is available at **http://localhost:5000**

### Terraform and Vault

Full version: Terraform rebuilds the platform (cluster, Kyverno, Vault, monitoring, Falco, Argo CD and Image Updater), and Argo CD deploys the application. The cluster runs the image signed by the pipeline, pulled from GitHub Container Registry; Kyverno verifies its signature before any pod starts. Secrets are encrypted in Vault and injected at pod startup by a sidecar; each pod authenticates with its own ServiceAccount, with read-only, time-limited access. Outbound traffic is restricted: pods can only reach the cluster DNS and Vault.

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

After a Docker or PC restart, start the Kind node, then unseal Vault:

```
docker start rpg-pipeline-control-plane
.\vault\unseal-vault.ps1
kubectl delete pod -n rpg-pipeline --all
```

</details>

The API is available at **http://localhost:5000**

## GitOps

Argo CD deploys the application from `k8s/` on the `main` branch, so only code that has passed every check reaches the cluster. It keeps the cluster identical to Git: a manual change or a deleted resource is reverted automatically, within seconds. Terraform builds the platform, Argo CD manages the application, and Kyverno still checks everything Argo CD creates. Argo CD Image Updater watches the `main` tag on GitHub Container Registry: when the pipeline signs a new image, it records the new digest and Argo CD deploys it, with no manual step.

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

Prometheus collects cluster state and API metrics, and Grafana displays them in dashboards. An alert fires when there are more than 10 rejected logins within 5 minutes. Falco detections raise alerts too, as does Falco itself going silent.

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

The script fetches the monsters from the live API and updates `monsters.csv` before launching the game.

## Tools Used

- **CI/CD & infrastructure**: GitHub Actions, Docker, Docker Hardened Images, Kubernetes (Kind), Helm, Terraform, Argo CD, Alpine Linux, Dependabot
- **Security**: Gitleaks, Trivy, Bandit, Semgrep, OWASP ZAP, Cppcheck, Checkov, Kyverno, Falco, Syft, Cosign, HashiCorp Vault
- **Backend & testing**: Flask, Gunicorn, SQLite, JWT, pytest
- **Observability**: Prometheus, Grafana

## Source Project

The RPG game code (S6 project): [Alterdune](https://github.com/Maxime-H-DA/Alterdune)
