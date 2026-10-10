$ErrorActionPreference = "Stop"

$fichierCles = Join-Path $PSScriptRoot "..\.vault-keys\vault-unseal-keys.xml"

if (-not (Test-Path $fichierCles)) {
    Write-Host "Aucune cle trouvee dans $fichierCles. Lance d'abord init-vault.ps1."
    exit 1
}

kubectl wait --for=jsonpath='{.status.phase}'=Running pod/vault-0 -n vault --timeout=180s

$keys = Import-Clixml $fichierCles | ForEach-Object { [System.Net.NetworkCredential]::new("", $_).Password }

kubectl exec -n vault vault-0 -- vault operator unseal $keys[0] | Out-Null
kubectl exec -n vault vault-0 -- vault operator unseal $keys[1] | Out-Null
kubectl exec -n vault vault-0 -- vault operator unseal $keys[2] | Out-Null
$keys = $null

kubectl exec -n vault vault-0 -- vault status
