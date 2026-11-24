param([string] $Python = ".venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    npm.cmd --prefix frontend ci
    npm.cmd --prefix frontend run build
    npm.cmd --prefix desktop ci
    $FrontendDist = (Resolve-Path frontend\dist).Path
    & $Python -m PyInstaller --noconfirm --clean --onedir --name ai-tutor-service `
        --specpath dist\pyinstaller --workpath dist\pyinstaller\work --distpath dist\backend `
        --paths $PWD.Path --add-data "${FrontendDist}:frontend/dist" --hidden-import uvicorn.logging `
        --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.protocols.http.h11_impl `
        --hidden-import uvicorn.lifespan.on tutor\desktop.py
    npm.cmd --prefix desktop run package:win
}
finally {
    Pop-Location
}
