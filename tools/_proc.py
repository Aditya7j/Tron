"""_proc.py - the one place in this house that knows how to start a child process.

WHY IT EXISTS, measured rather than assumed. Every spoken answer flashed a black window
on the boss's desktop. The cause was not a hand and not an organ tick: it was `say.py`
handing piper to `subprocess.run()` with the default creation flags. Windows then gives the
child a console of its own, and a console has a window. Caught in the act by a tight
user32 poll while POST /say was in flight:

    HIT  +2,300ms  pid 45448  class PseudoConsoleWindow
          chain: piper.exe(45448) <- python.exe(42376)

Two details of that line are the whole reason this module is a module and not a flag typed
into one call:

  THE CLASS IS `PseudoConsoleWindow`, NOT `ConsoleWindowClass`. The server is started from
    a shell that owns a ConPTY, so its console children get a pseudo-console, and the
    pseudo-console's window is a different window class from the one every answer on the
    subject names. A detector - or a reader - looking only for `ConsoleWindowClass` sees
    nothing and concludes there is nothing to fix.
  THE PARENT IS THE SERVER. Any process the server starts inherits this, which means the
    policy cannot live at one call site. A hand added next month would flash again, and
    nobody would connect the flash to the hand.

THE POLICY. On win32, inject `creationflags=CREATE_NO_WINDOW` (0x08000000) unless the
caller has an opinion of its own - a caller that passes any `creationflags` gets exactly
what it asked for, because DETACHED_PROCESS and CREATE_NEW_CONSOLE are deliberate choices
and silently or-ing a contradictory flag into them is how a launcher stops launching.
Everywhere else this is `subprocess` with the arguments you passed and no cleverness at
all, so a Mac or a Linux box behaves exactly as it did before.

CREATE_NO_WINDOW rather than STARTUPINFO/SW_HIDE: SW_HIDE hides a window that has already
been created, which is a race - the flash can happen before the hide lands - and it does
nothing at all for a console the OS allocates on the child's behalf. NO_WINDOW means the
console is never allocated, so there is no window to hide and no race to lose.

Used by say.py (piper), hands.py (every registry hand), tools/relaunch_chrome.py
(powershell), focus.py's mac and linux readers, preflight.py and test_email_wiring.py.
"""
import subprocess
import sys

# 0x08000000. Named on the module rather than read from subprocess every call, because
# subprocess.CREATE_NO_WINDOW does not exist off Windows and this file is imported there.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# Set by _quiet() so a probe - preflight's check 21 - can prove the policy fired rather
# than taking the absence of a window as evidence on a machine that might not have shown
# one anyway. Nothing reads it in the ordinary course of business.
applied = 0


def _quiet(kwargs):
    """Add the flag on Windows, and only if the caller has not spoken for itself."""
    global applied
    if sys.platform != "win32":
        return kwargs
    if kwargs.get("creationflags"):
        return kwargs                       # the caller's choice wins, untouched
    kwargs["creationflags"] = CREATE_NO_WINDOW
    applied += 1
    return kwargs


def run(*args, **kwargs):
    """subprocess.run, with no console window on Windows."""
    return subprocess.run(*args, **_quiet(kwargs))


def popen(*args, **kwargs):
    """subprocess.Popen, with no console window on Windows."""
    return subprocess.Popen(*args, **_quiet(kwargs))
