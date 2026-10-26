$fichierEnv = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $fichierEnv)) { throw "Fichier .env introuvable : $fichierEnv" }

$valeurs = @{}
Get-Content $fichierEnv -Encoding UTF8 | Where-Object { $_ -match "^\s*[^#].*=" } | ForEach-Object {
    $key, $value = $_ -split "=", 2
    $valeurs[$key.Trim()] = $value.Trim().Trim('"', "'")
}

$secrets = @{}
foreach ($nom in "ADMIN_USERNAME", "ADMIN_PASSWORD", "API_SECRET_KEY") {
    if (-not $valeurs[$nom]) { throw "Variable $nom absente ou vide dans .env" }
    $secrets[$nom] = $valeurs[$nom]
}

[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::InputEncoding
$secrets | ConvertTo-Json -Compress | kubectl exec -i -n vault vault-0 -- vault kv put secret/rpg-api -
