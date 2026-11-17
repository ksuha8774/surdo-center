param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
$secretBytes = New-Object byte[] 48
$passwordBytes = New-Object byte[] 24
$random.GetBytes($secretBytes)
$random.GetBytes($passwordBytes)
$random.Dispose()

$secret = ($secretBytes | ForEach-Object { $_.ToString("x2") }) -join ""
$password = ($passwordBytes | ForEach-Object { $_.ToString("x2") }) -join ""

@(
    "DJANGO_SECRET_KEY=$secret"
    "DJANGO_DEBUG=1"
    "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost"
    "POSTGRES_DB=surdo_center"
    "POSTGRES_USER=surdo_center_app"
    "POSTGRES_PASSWORD=$password"
    "POSTGRES_HOST=127.0.0.1"
    "POSTGRES_PORT=5432"
    "POSTGRES_CONN_MAX_AGE=60"
    "POSTGRES_CONNECT_TIMEOUT=5"
) | Set-Content -LiteralPath $OutputPath -Encoding Ascii
