# build-sidecar.ps1 - 构建 cc-spec sidecar

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ViewerRoot = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ViewerRoot)
$SidecarDir = Join-Path $ViewerRoot "sidecar"
$TauriSidecarDir = Join-Path $ViewerRoot "src-tauri\\sidecar"
$SpecFile = Join-Path $SidecarDir "cc-spec.spec"
$SrcPath = Join-Path $ProjectRoot "src"

Write-Host "=== Building cc-spec sidecar ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "Sidecar dir: $SidecarDir"

# 确保 sidecar 目录存在
if (-not (Test-Path $SidecarDir)) {
    New-Item -ItemType Directory -Path $SidecarDir -Force | Out-Null
}
if (-not (Test-Path $TauriSidecarDir)) {
    New-Item -ItemType Directory -Path $TauriSidecarDir -Force | Out-Null
}

# 切换到项目根目录
Push-Location $ProjectRoot

try {
    # 检查 PyInstaller 是否安装
    Write-Host "`nChecking PyInstaller..." -ForegroundColor Yellow
    $pyinstallerCheck = & uv run python -c "import PyInstaller" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
        & uv pip install pyinstaller
    }

    # 运行 PyInstaller
    Write-Host "`nRunning PyInstaller..." -ForegroundColor Yellow
    & uv run pyinstaller --clean $SpecFile

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed"
    }

    # 复制输出文件到 sidecar 目录
    $DistPath = Join-Path $ProjectRoot "dist"
    $ExeName = if ($IsWindows -or $env:OS -match "Windows") { "cc-spec.exe" } else { "cc-spec" }
    $SourceExe = Join-Path $DistPath $ExeName
    $TargetExe = Join-Path $SidecarDir $ExeName

    if (Test-Path $SourceExe) {
        Write-Host "`nCopying sidecar to: $TargetExe" -ForegroundColor Yellow
        Copy-Item $SourceExe $TargetExe -Force

        # 创建平台特定的名称
        $Arch = if ([Environment]::Is64BitOperatingSystem) { "x86_64" } else { "i686" }
        $Platform = if ($IsWindows -or $env:OS -match "Windows") { "pc-windows-msvc" } else { "unknown-linux-gnu" }
        $TargetName = "cc-spec-$Arch-$Platform"
        if ($IsWindows -or $env:OS -match "Windows") { $TargetName += ".exe" }
        $TargetPlatformExe = Join-Path $SidecarDir $TargetName

        Copy-Item $SourceExe $TargetPlatformExe -Force
        Write-Host "Created platform-specific sidecar: $TargetName" -ForegroundColor Green

        # 同步到 Tauri externalBin 目录（src-tauri/sidecar）
        $TauriTargetPlatformExe = Join-Path $TauriSidecarDir $TargetName
        Copy-Item $SourceExe $TauriTargetPlatformExe -Force
        Write-Host "Copied to Tauri sidecar: $TauriTargetPlatformExe" -ForegroundColor Green

        # 显示文件大小
        $Size = (Get-Item $TargetExe).Length / 1MB
        Write-Host "`nSidecar size: $([math]::Round($Size, 2)) MB" -ForegroundColor Cyan
    } else {
        throw "Build output not found: $SourceExe"
    }

    Write-Host "`n=== Build complete! ===" -ForegroundColor Green

} finally {
    Pop-Location
}
