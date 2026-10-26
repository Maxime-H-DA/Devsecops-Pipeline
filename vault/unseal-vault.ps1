$ErrorActionPreference = "Stop"

function Verifier($etape) {
    if ($LASTEXITCODE -ne 0) { throw "Echec : $etape" }
}

function ApiKubernetesPrete {
    $ErrorActionPreference = "Continue"
    kubectl get --raw /readyz 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
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

$fichierCles = Join-Path $PSScriptRoot "..\.vault-keys\vault-unseal-keys.xml"

if (-not (Test-Path $fichierCles)) {
    Write-Host "Aucune cle trouvee dans $fichierCles. Lance d'abord init-vault.ps1."
    exit 1
}

Write-Host "Demarrage du noeud Kind..."
docker start rpg-pipeline-control-plane | Out-Null
Verifier "demarrage du noeud Kind (Docker est-il lance ?)"

Write-Host "Attente de Kubernetes..."
for ($i = 0; $i -lt 40 -and -not (ApiKubernetesPrete); $i++) { Start-Sleep -Seconds 3 }
kubectl wait --for=condition=Ready node --all --timeout=120s
Verifier "attente du noeud Kubernetes"

Write-Host "Attente de Vault..."
$etat = AttendreVault

if ($etat.sealed) {
    Write-Host "Descellement..."
    $keys = Import-Clixml $fichierCles | ForEach-Object { [System.Net.NetworkCredential]::new("", $_).Password }
    foreach ($key in $keys[0..2]) {
        kubectl exec -n vault vault-0 -- vault operator unseal $key | Out-Null
        Verifier "descellement"
    }
    $keys = $null
}

$etat = EtatVault
if (-not $etat -or $etat.sealed) { throw "Echec : Vault est toujours scelle" }
Write-Host "Vault est descelle."

Write-Host "Redemarrage de l'API..."
kubectl rollout restart deployment/rpg-api -n rpg-pipeline
Verifier "redemarrage de l'API"
kubectl rollout status deployment/rpg-api -n rpg-pipeline --timeout=180s
Verifier "demarrage de l'API"
