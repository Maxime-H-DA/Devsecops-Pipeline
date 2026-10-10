$ErrorActionPreference = "Stop"

function Verifier($etape) {
    if ($LASTEXITCODE -ne 0) { throw "Echec : $etape" }
}

$dossierCles = Join-Path $PSScriptRoot "..\.vault-keys"
$fichierCles = Join-Path $dossierCles "vault-unseal-keys.xml"

if (Test-Path $fichierCles) {
    Write-Host "Des cles existent deja dans $fichierCles. Vault est sans doute deja initialise : utilise unseal-vault.ps1."
    exit 1
}

Write-Host "Attente du demarrage de Vault..."
kubectl wait --for=jsonpath='{.status.phase}'=Running pod/vault-0 -n vault --timeout=180s
Verifier "attente de Vault"

Write-Host "Initialisation de Vault..."
$init = kubectl exec -n vault vault-0 -- vault operator init -key-shares=5 -key-threshold=3 -format=json | ConvertFrom-Json
Verifier "initialisation de Vault"
$keys = $init.unseal_keys_b64
$token = $init.root_token

New-Item -ItemType Directory -Force $dossierCles | Out-Null
$keys | ForEach-Object { ConvertTo-SecureString $_ -AsPlainText -Force } | Export-Clixml $fichierCles
Write-Host "Cles de descellement chiffrees et sauvegardees dans $fichierCles"

Write-Host "Descellement..."
kubectl exec -n vault vault-0 -- vault operator unseal $keys[0] | Out-Null
kubectl exec -n vault vault-0 -- vault operator unseal $keys[1] | Out-Null
kubectl exec -n vault vault-0 -- vault operator unseal $keys[2] | Out-Null
Verifier "descellement"
kubectl exec -n vault vault-0 -- vault login -no-print $token
Verifier "connexion a Vault"

Write-Host "Configuration..."
kubectl exec -n vault vault-0 -- vault auth enable kubernetes
Verifier "activation de l'authentification Kubernetes"
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443"
Verifier "configuration de l'authentification Kubernetes"
kubectl exec -n vault vault-0 -- vault secrets enable -path=secret kv-v2
Verifier "activation du moteur de secrets"

cmd /c "kubectl exec -i -n vault vault-0 -- vault policy write rpg-api - < vault\policies\rpg-api-policy.hcl"
Verifier "ecriture de la policy Vault"
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/rpg-api bound_service_account_names=rpg-api bound_service_account_namespaces=rpg-pipeline policies=rpg-api ttl=1h
Verifier "creation du role rpg-api"

kubectl exec -n vault vault-0 -- mkdir -p /vault/audit
kubectl exec -n vault vault-0 -- chmod u+x /vault/audit
kubectl exec -n vault vault-0 -- vault audit enable file file_path=/vault/audit/audit.log
Verifier "activation de l'audit"

Write-Host "Injection des secrets..."
.\vault\seed-secrets.ps1
Verifier "injection des secrets"

Write-Host "Revocation du token root..."
kubectl exec -n vault vault-0 -- vault token revoke -self
$token = $null
$keys = $null

Write-Host "Redemarrage de l'API..."
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
kubectl rollout status deployment/rpg-api -n rpg-pipeline --timeout=180s
