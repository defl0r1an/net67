# Готовит свежую копию репозитория к запуску.
#
# Два файла не хранятся в git и потому отсутствуют после `git clone`:
#
#   src\config\build_info.py    — номер версии и канал
#   src\config\_build_secrets.py — токены сборки (у нас пустые)
#
# Первый исключён, потому что его подставляет сборка. Второй — потому
# что это файл секретов по назначению, и класть его в репозиторий нельзя
# даже пустым: однажды он окажется непустым.
#
# Без них приложение не стартует: `from config.build_info import
# APP_VERSION` падает на первой же строке запуска. Скрипт создаёт оба,
# если их нет, и не трогает уже существующие.
#
# Запуск из корня репозитория:
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap_dev.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$config = Join-Path $root "src\config"

if (-not (Test-Path $config)) {
    throw "Запускать из корня репозитория: не найден $config"
}

$version = "0.5.67"

$buildInfo = Join-Path $config "build_info.py"
if (Test-Path $buildInfo) {
    Write-Host "build_info.py уже есть, не трогаю"
} else {
    @(
        "# Генерируется на сборке. Здесь - локальная заглушка для прогона тестов."
        "APP_VERSION = `"$version`""
        "CHANNEL = `"stable`""
    ) | Set-Content -Path $buildInfo -Encoding UTF8
    Write-Host "создан build_info.py ($version)"
}

$secrets = Join-Path $config "_build_secrets.py"
if (Test-Path $secrets) {
    Write-Host "_build_secrets.py уже есть, не трогаю"
} else {
    @(
        '"""Генерируется на сборке. Здесь - пустая заглушка."""'
        ""
        "UPDATE_SERVERS: list[str] = []"
        'GITHUB_UPDATE_TOKEN = ""'
        'TG_UPDATE_BOT_TOKEN = ""'
        "PROXY_PRESETS: list = []"
        'MTPROXY_LINK = ""'
    ) | Set-Content -Path $secrets -Encoding UTF8
    Write-Host "создан _build_secrets.py (пустой)"
}

Write-Host ""
Write-Host "Дальше:"
Write-Host "  pip install -r requirements-runtime.txt"
Write-Host "  python src\main.py"
