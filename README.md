![Pipeline](https://github.com/Maxime-H-DA/devsecops-pipeline/actions/workflows/pipeline.yml/badge.svg)

# DevSecOps Pipeline

End-to-end DevSecOps platform, from commit to production: secure CI/CD pipeline, hardened Kubernetes deployment, infrastructure defined in Terraform, secrets in HashiCorp Vault, and monitoring with Prometheus/Grafana.

All of it is applied to a Flask API running in production at [rpg-pipeline.onrender.com](https://rpg-pipeline.onrender.com), which serves the monsters of a C++ RPG game. The goal wasn't the application itself, but to reproduce the practices of an enterprise DevOps team.

**At a glance**
- 10 CI jobs on every push and pull request, 8 of them blocking: merging is impossible if any of them fails
- 45 unit tests, including attack tests
- 189 Trivy alerts triaged, HTTP (ZAP) and Kubernetes (Checkov) misconfigurations fixed
- 16 Terraform resources to rebuild the entire environment
- 4 Kyverno policies in enforce mode
- Secrets encrypted in Vault, never stored in plaintext in the cluster

## CI/CD Pipeline

```
push / pull request -> main
 |
 |-- in parallel, blocking:
 |    |-- analyse-code: Gitleaks + Cppcheck (C++ code)
 |    |-- scan-jeu: Docker build (game) + Trivy
 |    |-- scan-api: Docker build (API) + Trivy
 |    |-- sast-api: Bandit + Semgrep
 |    |-- tests-api: pytest
 |    |-- iac-scan-checkov: Kubernetes manifests, Helm chart and Terraform
 |    |-- kyverno-policy-test: Kyverno policies replayed against the manifests
 |    `-- terraform-check: Terraform code formatting and validation
 |
 |-- in parallel, non-blocking:
 |    `-- dast-api: OWASP ZAP against the live API (Render)
 |
 `-- after the 8 blocking jobs, on main only:
      `-- supply-chain-api: image publishing, SBOM (Syft) + signing (Cosign)
```

Scans run before the merge, not after, and only an image that has passed every check is published and signed. Pre-commit hooks rerun most of these checks locally before the push even happens, results show up in the **Security > Code scanning** tab, and Dependabot keeps dependencies up to date by going through the same checks.

## Deployment

### Docker

The quickest way to run the API locally.

<details>
<summary>Commands</summary>

```
docker build -t rpg-api -f rpg-api/Dockerfile .
docker run -d -p 5000:5000 --env-file .env -v rpg-data:/app/data rpg-api
```

</details>

The API is available at **http://localhost:5000**

### Helm

First version of the Kubernetes deployment (Kind), before Vault: non-root container, read-only filesystem, resource limits, health probes and NetworkPolicy. Secrets still go through a Kubernetes `Secret`.

<details>
<summary>Commands</summary>

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

The API is available at **http://localhost:5000**

### Terraform and Vault

Full version: Terraform rebuilds the cluster, Kyverno, Vault, the application and the monitoring stack. Secrets are encrypted in Vault and injected at pod startup by a sidecar; each pod authenticates with its own ServiceAccount, with read-only, time-limited access.

<details>
<summary>Commands</summary>

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

# Unseal keys: keep them outside the repo, required to unseal Vault again
$keys

kubectl port-forward -n rpg-pipeline svc/rpg-api 5000:80
```

</details>

The API is available at **http://localhost:5000**

## Monitoring

Prometheus collects cluster state and API metrics, and Grafana displays them in dashboards. An alert fires when there are more than 10 rejected logins within 5 minutes.

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

- **CI/CD & infrastructure**: GitHub Actions, Docker, Kubernetes (Kind), Helm, Terraform, Alpine Linux, Dependabot
- **Security**: Gitleaks, Trivy,
