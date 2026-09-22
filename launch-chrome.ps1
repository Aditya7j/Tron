<#
  launch-chrome.ps1 - the browser a focus session can actually watch.

  Tab-level locking needs Chrome's DevTools port. Forgetting the flag is not a small
  thing: the session still runs, but it can only watch the APPLICATION, so every tab
  in the browser looks like the one you promised to work in. The whole feature turns
  into "is Chrome in front", which is not what you asked for.

  So this is the launcher. One double-click:

      1. closes any stray browser of the same family (a browser already running
         without the port would just be joined to, and its port is not open),
      2. starts it again with --remote-debugging-port=9222,
      3. opens the viewer at http://127.0.0.1:4700,
      4. and then PROVES it worked - it asks the port for its version, asks the
         server what /health now reports, and says plainly if either is wrong.

  Step 4 is the point of having a script at all. A launcher that opens a browser and
  assumes is a launcher you will trust on the one day it silently failed.

  ---------------------------------------------------------------------------------
  ANOTHER BROWSER? Change the one line marked THE ONE LINE below: 'msedge' or
  'brave' instead of 'chrome'. The port flag and the CDP join are identical across
  every Chromium browser - focus.py asks for /json/list and gets the same answer -
  so nothing else in this file or in the app needs to change.
  ---------------------------------------------------------------------------------

  Usage:  double-click the desktop shortcut, or
          powershell -ExecutionPolicy Bypass -File launch-chrome.ps1
          powershell -ExecutionPolicy Bypass -File launch-chrome.ps1 -Port 9223

  The desktop shortcut is made BY this file, so it can be made again after the
  project moves - and so there is nowhere else to keep the arguments in sync:

          powershell -ExecutionPolicy Bypass -File launch-chrome.ps1 -MakeShortcut
#>

[CmdletBinding()]
param(
  [string] $Url  = 'http://127.0.0.1:4700/',   # the viewer
  [int]    $Port = 9222,                       # focus.py looks at 9222, 9223, 9224
  [switch] $Stay,                              # keep this window open on success too
  [switch] $MakeShortcut                       # put a shortcut to me on the Desktop
)

# ---- THE ONE LINE: which browser this machine uses -------------------------------
$Browser = 'chrome'          # 'chrome' | 'msedge' | 'brave'
# ---------------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'

$FAMILY = @{
  chrome = @{ Image = 'chrome.exe'
              Paths = @('Google\Chrome\Application\chrome.exe') }
  msedge = @{ Image = 'msedge.exe'
              Paths = @('Microsoft\Edge\Application\msedge.exe') }
  brave  = @{ Image = 'brave.exe'
              Paths = @('BraveSoftware\Brave-Browser\Application\brave.exe') }
}

function Say  ($m) { Write-Host "  $m" }
function Good ($m) { Write-Host "  ok    $m" -ForegroundColor Green }
function Bad  ($m) { Write-Host "  FAIL  $m" -ForegroundColor Red }
function Warn ($m) { Write-Host "  warn  $m" -ForegroundColor Yellow }

function Finish ([int] $code) {
  # A failure always waits for you. A success waits only if you asked it to, because
  # the reason this exists is that it should be one double-click and then your work.
  if ($code -ne 0 -or $Stay) {
    Write-Host ''
    Write-Host '  press Enter to close' -ForegroundColor DarkGray
    try { [void](Read-Host) } catch { Start-Sleep -Seconds 20 }
  }
  exit $code
}

Write-Host ''
Write-Host "  Jarvis - launching $Browser with the DevTools port open" `
           -ForegroundColor Cyan
Write-Host ''

if (-not $FAMILY.ContainsKey($Browser)) {
  Bad "unknown browser '$Browser' - pick one of: $($FAMILY.Keys -join ', ')"
  Finish 2
}
$image = $FAMILY[$Browser].Image

# -- 0. where is it? ---------------------------------------------------------------
# Three roots, because a Chromium browser can be installed per-machine or per-user and
# both are ordinary. Whichever exists first wins.
$roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) |
         Where-Object { $_ }
$exe = $null
foreach ($root in $roots) {
  foreach ($tail in $FAMILY[$Browser].Paths) {
    $try = Join-Path $root $tail
    if (Test-Path -LiteralPath $try) { $exe = $try; break }
  }
  if ($exe) { break }
}
if (-not $exe) {
  # Last resort: ask Windows itself where the image lives.
  $key = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\$image"
  if (Test-Path $key) { $exe = (Get-ItemProperty $key).'(default)' }
}
if (-not $exe -or -not (Test-Path -LiteralPath $exe)) {
  Bad "cannot find $image - install it, or change the browser on THE ONE LINE"
  Finish 2
}
Say "browser: $exe"

# -- 0a. -MakeShortcut: install the double-click and stop -------------------------
# A .ps1 cannot be double-clicked (Windows opens it in an editor), so the shortcut
# targets powershell.exe and passes this file - which is also where -ExecutionPolicy
# Bypass belongs: scoped to one shortcut, not turned on for the machine.
if ($MakeShortcut) {
  $me      = $MyInvocation.MyCommand.Path
  $desktop = [Environment]::GetFolderPath('Desktop')   # follows a OneDrive redirect
  $lnk     = Join-Path $desktop 'Jarvis Chrome (DevTools).lnk'
  $shell   = New-Object -ComObject WScript.Shell
  $sc      = $shell.CreateShortcut($lnk)
  $sc.TargetPath       = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $sc.Arguments        = "-NoProfile -ExecutionPolicy Bypass -File `"$me`""
  $sc.WorkingDirectory = Split-Path -Parent $me
  $sc.IconLocation     = "$exe,0"                      # it looks like what it opens
  $sc.Description      = 'Kill stray Chrome, relaunch it with --remote-debugging-port=9222, open the Jarvis viewer'
  $sc.WindowStyle      = 7                             # start minimised; it is a porch light
  $sc.Save()
  if (Test-Path -LiteralPath $lnk) { Good "shortcut: $lnk" } else { Bad 'the shortcut was not written' ; Finish 2 }
  Say 'double-click it whenever you sit down to work.'
  Finish 0
}

# -- 1. is the server even up? -----------------------------------------------------
# Said before the browser opens, because a viewer tab pointed at nothing is a
# confusing way to find out that server.py is not running.
$serverUp = $false
try {
  $h = Invoke-RestMethod -Uri 'http://127.0.0.1:4700/health' -TimeoutSec 4
  $serverUp = [bool]$h.ok
} catch { $serverUp = $false }
if ($serverUp) { Say 'server: up on 127.0.0.1:4700' }
else { Warn 'the server is NOT answering on 127.0.0.1:4700 - start it with "python server.py"' }

# -- 2. close the strays -----------------------------------------------------------
# Not tidiness. A browser that is already running OWNS the profile, so a second
# launch hands the URL to the running one and exits - and the running one has no
# port. Killing it is the only way "always the right browser" can be true.
$running = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($image)) `
             -ErrorAction SilentlyContinue)
if ($running.Count) {
  Say "closing $($running.Count) stray $image process(es)"
  taskkill /IM $image /F 2>&1 | Out-Null
  Start-Sleep -Milliseconds 1200          # let the profile lock actually go
} else {
  Say "no $image running"
}

# -- 3. the launch ----------------------------------------------------------------
# --user-data-dir is NOT optional, and this is the part everyone loses an evening to:
# since Chrome 136 the DevTools port is REFUSED for the default profile - a real
# security fix, since any local process could otherwise read your logged-in browser.
# So the port lives in a profile of its own. It is persistent (not a temp dir), so
# your logins and tabs in it survive between launches; it is simply not the profile
# your ordinary browsing uses.
$profileDir = Join-Path $env:LOCALAPPDATA "Jarvis\devtools-profile-$Browser"
if (-not (Test-Path -LiteralPath $profileDir)) {
  New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
Say "profile: $profileDir"

$argline = @(
  "--remote-debugging-port=$Port",
  "--remote-allow-origins=*",        # the viewer's own origin may join the port
  "--user-data-dir=`"$profileDir`"",
  '--no-first-run',
  '--no-default-browser-check',
  '--new-window',
  "`"$Url`""
) -join ' '

Say "launching with --remote-debugging-port=$Port"
Start-Process -FilePath $exe -ArgumentList $argline | Out-Null

# -- 4. prove it ------------------------------------------------------------------
$version = $null
for ($i = 0; $i -lt 60; $i++) {
  try {
    $version = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    break
  } catch { Start-Sleep -Milliseconds 300 }
}
if (-not $version) {
  Bad "the DevTools port $Port never answered - tab-level locking would be unavailable"
  Say 'things worth checking: another browser of the same family still running,'
  Say 'a profile lock left behind, or an enterprise policy disabling remote debugging.'
  Finish 2
}
Good "DevTools port $Port is open - $($version.Browser)"

# And the answer that actually matters: what the SERVER can see. focus.py caches
# capability() for a few seconds, so this waits out the cache rather than reporting a
# boolean that was true before the browser existed.
if ($serverUp) {
  Start-Sleep -Milliseconds 3600
  $cdp = $false
  for ($i = 0; $i -lt 8; $i++) {
    try {
      $f = (Invoke-RestMethod -Uri 'http://127.0.0.1:4700/health' -TimeoutSec 6).focus
      if ($f.cdp) { $cdp = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 900
  }
  if ($cdp) {
    Good '/health reports focus.cdp = true - a session can lock the SITE, not just the app'
  } else {
    Warn '/health still reports focus.cdp = false. The port is open, so this usually'
    Warn 'means the browser has not painted a page yet - check the FOCUS debug overlay'
    Warn 'in a moment. If it stays false, a session will say "application only" out loud.'
  }
}

Write-Host ''
Say 'Go on then, sir. Click FOCUS.'
Finish 0
