$ErrorActionPreference = "Stop"
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::InputEncoding

function Verifier($etape) {
    if ($LASTEXITCODE -ne 0) { throw "Echec : $etape" }
}

function EtatVault {
    $ErrorActionPreference = "Continue"
    $etat = kubectl exec -n vault vault-0 -- vault status -format=json 2>$null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) { return $null }
    return ($etat -join "`n") | ConvertFrom-Json
}

function AttendreVault {
    for ($i = 0; $i -lt 60; $i++) {
        $etat = EtatVault
        if ($etat) { return $etat }
        Start-Sleep -Seconds 3
    }
    throw "Echec : Vault ne repond pas apres 3 minutes"
}

$dossierCles = Join-Path $PSScriptRoot "..\.vault-keys"
$fichierCles = Join-Path $dossierCles "vault-unseal-keys.xml"

Write-Host "Attente du demarrage de Vault..."
$etat = AttendreVault

if ($etat.initialized) {
    Write-Host "Vault est deja initialise : utilise unseal-vault.ps1."
    exit 1
}
if (Test-Path $fichierCles) {
    Write-Host "Cles d'un ancien cluster trouvees, elles vont etre remplacees."
}

Write-Host "Initialisation de Vault..."
$init = kubectl exec -n vault vault-0 -- vault operator init -key-shares=5 -key-threshold=3 -format=json | ConvertFrom-Json
Verifier "initialisation de Vault"
$keys = $init.unseal_keys_b64
$token = $init.root_token

New-Item -ItemType Directory -Force $dossierCles | Out-Null
$keys | ForEach-Object { ConvertTo-SecureString $_ -AsPlainText -Force } | Export-Clixml $fichierCles
Write-Host "Cles de descellement chiffrees et sauvegardees dans $fichierCles"

Write-Host "Descellement..."
foreach ($key in $keys[0..2]) {
    kubectl exec -n vault vault-0 -- vault operator unseal $key | Out-Null
    Verifier "descellement"
}
kubectl exec -n vault vault-0 -- vault login -no-print $token
Verifier "connexion a Vault"

Write-Host "Configuration..."
kubectl exec -n vault vault-0 -- vault auth enable kubernetes
Verifier "activation de l'authentification Kubernetes"
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443"
Verifier "configuration de l'authentification Kubernetes"
kubectl exec -n vault vault-0 -- vault secrets enable -path=secret kv-v2
Verifier "activation du moteur de secrets"

Get-Content (Join-Path $PSScriptRoot "policies\rpg-api-policy.hcl") -Raw | kubectl exec -i -n vault vault-0 -- vault policy write rpg-api -
Verifier "ecriture de la policy Vault"
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/rpg-api bound_service_account_names=rpg-api bound_service_account_namespaces=rpg-pipeline policies=rpg-api ttl=1h
Verifier "creation du role rpg-api"

kubectl exec -n vault vault-0 -- vault audit enable file file_path=/vault/audit/audit.log
Verifier "activation de l'audit"

Write-Host "Injection des secrets..."
& (Join-Path $PSScriptRoot "seed-secrets.ps1")
Verifier "injection des secrets"

Write-Host "Revocation du token root..."
kubectl exec -n vault vault-0 -- vault token revoke -self
Verifier "revocation du token root"
$token = $null
$keys = $null

Write-Host "Redemarrage de l'API..."
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
Verifier "redemarrage de l'API"
kubectl rollout status deployment/rpg-api -n rpg-pipeline --timeout=180s
Verifier "demarrage de l'API"
