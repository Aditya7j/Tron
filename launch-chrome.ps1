<#
  launch-chrome.ps1 - the browser a focus session can actually watch.

  Tab-level locking needs Chrome's DevTools port. Forgetting the flag is not a small
  thing: the session still runs, but it can only watch the APPLICATION, so every tab
  in the browser looks like the one you promised to work in. The whole feature turns
  into "is Chrome in front", which is not what you asked for.

  So this is the launcher. One double-click:

      1. closes any browser already running ON THIS SCRIPT'S OWN PROFILE -
         politely, so its tabs come back - because a browser holding that profile
         would swallow the launch and exit, and its port is not open. Every OTHER
         browser on the machine is left alone: measured on this box, a second
         Chrome on its own --user-data-dir opened the port in 332 ms with
         nineteen processes of ordinary browsing still running beside it.
      2. starts it again with --remote-debugging-port=9222 and
         --restore-last-session,
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
  [switch] $MakeShortcut,                      # put a shortcut to me on the Desktop
  [switch] $Quiet                              # never wait for a keypress: a script is running me
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
  # -Quiet is for the relaunch_chrome HAND, which runs this file with no console and a
  # timeout. "press Enter to close" with nobody there is a tool that hangs until it is
  # killed and then reports a failure that did not happen.
  if (-not $Quiet -and ($code -ne 0 -or $Stay)) {
    Write-Host ''
    Write-Host '  press Enter to close' -ForegroundColor DarkGray
    try { [void](Read-Host) } catch { Start-Sleep -Seconds 20 }
  }
  exit $code
}

Write-Host ''
Write-Host "  Galaxy - launching $Browser with the DevTools port open" `
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
  $lnk     = Join-Path $desktop 'Galaxy Chrome (DevTools).lnk'
  # He was called Jarvis until the persona block gave him a name. Sweep the old shortcut
  # away rather than leaving two icons that do the same thing, one of them with the wrong
  # name on it - a stale shortcut is the kind of thing that outlives three rewrites.
  $old     = Join-Path $desktop 'Jarvis Chrome (DevTools).lnk'
  if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Force }
  $shell   = New-Object -ComObject WScript.Shell
  $sc      = $shell.CreateShortcut($lnk)
  $sc.TargetPath       = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $sc.Arguments        = "-NoProfile -ExecutionPolicy Bypass -File `"$me`""
  $sc.WorkingDirectory = Split-Path -Parent $me
  $sc.IconLocation     = "$exe,0"                      # it looks like what it opens
  $sc.Description      = 'Close the DevTools-profile Chrome politely, start it again with --remote-debugging-port=9222 and its tabs restored, open the Galaxy viewer'
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

# -- 2. clear THIS PROFILE, and nothing else ---------------------------------------
# Not tidiness. A browser that is already running OWNS THE PROFILE it was started
# with, so a second launch on the same profile hands the URL to the running one and
# exits - and the running one has no port.
#
# The word that matters is "the same profile". This script used to run
# `taskkill /IM chrome.exe /F`, which is a different and much larger thing: on the
# day I measured it that would have killed nineteen processes of the boss's ordinary
# browsing - his real windows, in the DEFAULT profile, which this launch does not
# even reopen - to solve a lock contention that only ever involves the profile named
# below. A second Chrome on its own --user-data-dir needs none of them dead: it
# opened the port in 332 ms with all nineteen still running.
#
# And when this profile IS held, the close is POLITE. CloseMainWindow() posts the
# WM_CLOSE that the X button posts, Chrome exits cleanly, and a clean exit is the
# only kind that writes "Last Session" - which is what makes --restore-last-session
# below hand the tabs back. Measured both ways: after Stop-Process -Force the
# relaunch came back with one empty tab; after CloseMainWindow() it came back with
# every tab plus the viewer. A force kill is only for a straggler that ignores the
# polite request, and even then only for this profile.
# AND "IS IT GONE YET" IS A QUESTION ABOUT THE BROWSER PROCESS, NOT ABOUT EVERY PROCESS
# WEARING THE PROFILE'S NAME. This was the live defect, and it cost the thing the polite
# close exists for.
#   Chrome on one profile is eight processes: one browser, and seven helpers that carry the
#   same --user-data-dir on their command line - renderers, the GPU process, and a
#   --type=crashpad-handler which is the crash reporter and OUTLIVES the browser on purpose.
#   On this machine one was measured still running minutes after its browser had exited. The
#   wait below used to count all of them, so a crashpad handler that had not finished was
#   read as "something ignored WM_CLOSE" - and the fallback fired: Stop-Process -Force on
#   everything, including a browser that was in the middle of writing its session.
#   WHAT THE BOSS SAW: consent given, "I need Chrome relaunched with the debugging port" ->
#   Yes -> and his tabs did not come back. lock_proof caught it as "the relaunch restored his
#   work tab: " with nothing after the colon; in one run the forced kill left the profile
#   locked and the port never opened at all, which is the whole feature failing after he
#   said yes. Only the browser process holds the profile lock, only it has a window to send
#   WM_CLOSE to, and only its exit writes the session - so it is the only one worth waiting
#   for. The patience is fifteen seconds rather than eight because a clean exit with a dozen
#   tabs writes more than a clean exit with one.
$profileDir = Join-Path $env:LOCALAPPDATA "Jarvis\devtools-profile-$Browser"
# AND IT IS MATCHED ON THE PROFILE'S FOLDER NAME, NOT ON THE SPELLING OF ITS PATH. The
# filter used to be -like "*$profileDir*", which is an exact string match on a Windows path -
# so a browser holding THIS VERY PROFILE via "...\AppData\Local/Jarvis/devtools-profile-chrome"
# was invisible to it. Measured while chasing the defect above: the launcher reported no
# browser on the profile, launched a second Chrome, Chrome handed the command line to the one
# already holding the profile and exited, and the port never answered at all. The folder name
# is unique on this machine and immune to separator spelling.
$profileLeaf = "devtools-profile-$Browser"
# @() AT EVERY CALL SITE, NOT IN HERE, and it is not a style choice: PowerShell unrolls a
# function's output, so an @() built inside this function comes back as a bare CimInstance
# when there is exactly ONE browser - and $one.Count on a CimInstance is $null, not 1, so
# "if ($mine.Count)" was false in the commonest case there is. Measured: one portless Chrome
# holding the profile, reported as "no browser on this profile".
function Get-ProfileBrowsers {
  param($image, $profileLeaf)
  @(Get-CimInstance Win32_Process -Filter "Name='$image'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$profileLeaf*" -and
                   $_.CommandLine -notlike '*--type=*' })
}
$mine = @(Get-ProfileBrowsers $image $profileLeaf)
if ($mine.Count) {
  Say "closing $($mine.Count) $image browser process(es) on this profile - politely, so the tabs come back"
  foreach ($p in $mine) {
    $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne 0) { [void]$proc.CloseMainWindow() }
  }
  $gone = $false
  for ($i = 0; $i -lt 60; $i++) {          # up to 15 seconds of patience
    Start-Sleep -Milliseconds 250
    $left = @(Get-ProfileBrowsers $image $profileLeaf)
    if (-not $left.Count) { $gone = $true; break }
    # ---- ASK EVERY WINDOW, NOT JUST THE FIRST ----
    # CloseMainWindow() posts WM_CLOSE to ONE window: the one Windows currently calls main.
    # Chrome only exits when the last window has gone, and as each closes it promotes the
    # next to main. So a browser with two windows open on this profile - the boss with a
    # second window, or any run of this launcher that opened one - was asked once, closed
    # one window, stayed alive through the whole wait, and was then read as having ignored
    # WM_CLOSE and shot. That force kill is what cost the restored tabs: Chrome writes its
    # session on a clean exit, and --restore-last-session only works on a browser that was
    # closed, not one that was killed. Re-ask the newly promoted window about once a second
    # until the process is gone. An extra WM_CLOSE to a window already closing is harmless.
    if ($i % 4 -eq 3) {
      foreach ($p in $left) {
        $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($proc) {
          $proc.Refresh()
          if ($proc.MainWindowHandle -ne 0) { [void]$proc.CloseMainWindow() }
        }
      }
    }
  }
  if ($gone) {
    Good 'the profile is free and its session was written'
  } else {
    Warn 'a browser on this profile ignored WM_CLOSE; forcing only those processes'
    Get-ProfileBrowsers $image $profileLeaf |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 1200         # let the profile lock actually go
  }
} else {
  $helpers = @(Get-CimInstance Win32_Process -Filter "Name='$image'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and $_.CommandLine -like "*$profileLeaf*" }).Count
  if ($helpers) {
    Say "no $image browser on this profile - $helpers helper process(es) of a closed one, which hold nothing"
  } else {
    $others = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($image)) `
                -ErrorAction SilentlyContinue).Count
    if ($others) { Say "no $image on this profile; leaving the $others running elsewhere alone" }
    else { Say "no $image running" }
  }
}

# -- 3. the launch ----------------------------------------------------------------
# --user-data-dir is NOT optional, and this is the part everyone loses an evening to:
# since Chrome 136 the DevTools port is REFUSED for the default profile - a real
# security fix, since any local process could otherwise read your logged-in browser.
# So the port lives in a profile of its own. It is persistent (not a temp dir), so
# your logins and tabs in it survive between launches; it is simply not the profile
# your ordinary browsing uses.
# THE FOLDER NAME STAYS "Jarvis" ON PURPOSE, and this is the one place in the round where
# the old name survives. It is a directory path, not a string anybody reads, and it holds
# the boss's real logins and open tabs for the debugging browser. Renaming it would orphan
# all of that to make a folder he never opens say the right word - a cosmetic win paid for
# with his sessions. If it is ever moved, move the contents with it.
# ($profileDir was computed in step 2, which needed it to know whose processes were
# worth closing and whose were none of its business. One definition, because two would
# be a bug the first time one of them was edited.)
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
  # THE TABS COME BACK. Step 2 closed this profile politely precisely so that this
  # flag has a session to restore; measured, it returns every tab that was open and
  # then adds the viewer beside them. Harmless on a first run, where there is no
  # last session to restore and Chrome simply opens the URL.
  '--restore-last-session',
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
