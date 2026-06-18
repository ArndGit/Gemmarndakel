param(
    [string]$ShortcutPath = (Join-Path $PSScriptRoot "Gemmarndakel.lnk")
)

$targetPath = Join-Path $PSScriptRoot "DigitalerWahrsager.bat"
$iconPath = Join-Path $PSScriptRoot "kerzen-karo.ico"

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Launcher nicht gefunden: $targetPath"
}

if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Icon nicht gefunden: $iconPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.WindowStyle = 7
$shortcut.Description = "Gemmarndakel starten"
$shortcut.Save()
