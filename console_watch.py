"""console_watch.py - watch the Windows desktop for a console window that should not exist.

WHAT IT IS FOR. Part 0's promise is that nothing the server starts ever shows a console
window. That promise cannot be checked by reading the source, because it depends on how
Windows treats a child process, and it cannot be checked after the fact, because the window
lives for a few hundred milliseconds and then takes its evidence with it. So: a tight poll
of user32 while something is made to happen, and a verdict afterwards.

THREE THINGS IT KNOWS THAT A NAIVE VERSION WOULD NOT, each measured on this machine:

  THE CLASS IS NOT ALWAYS `ConsoleWindowClass`. The server is started from a shell holding a
    ConPTY, so its console children are given a pseudo-console whose window class is
    `PseudoConsoleWindow`. The real defect, caught before the fix, was exactly that class:

        HIT +2,300ms  pid 45448  class PseudoConsoleWindow
              chain: piper.exe(45448) <- python.exe(42376)

    A watcher that looked only for the famous class name would have reported a clean
    desktop and blessed the bug. All three classes are watched.
  THE WINDOW OUTLIVES NOTHING. By the time the caller asks for a verdict, the owning process
    is usually gone, so a pid looked up at the end resolves to nothing. The process map is
    therefore ACCUMULATED across polls and never pruned - a dead pid can still be named.
  ANCESTRY, NOT NAMES. This machine runs a third-party uninstaller task on a timer that
    spawns cmd.exe, and Windows Terminal owns a console window of its own at all times.
    Both showed up in the first probe. A hit only counts against us if its parent chain
    reaches the pid under test, which is what the mandate means by a parent-PID filter.

ONE VERDICT, AND IT IS THE WINDOW. The first version of this file also failed a run that
found a conhost.exe among the descendants, on the reasoning that CREATE_NO_WINDOW means no
console is allocated and therefore no console host is needed. That reasoning is wrong, and
an A/B on the real binary said so in the plainest possible way:

    MODE=old  (no creationflags)     windows: []   consoles: []
    MODE=new  (CREATE_NO_WINDOW)     windows: []   consoles: [conhost(37184) <- piper(42260)]

CREATE_NO_WINDOW does not mean "no console". It means "a console with no window": Windows
allocates one and hosts it in a conhost.exe that never shows itself. The unflagged spawn
allocated nothing because it INHERITED the console of the shell that started its parent.
So the naive rule had it exactly backwards - it would have passed the defect and failed the
repair, which is the worst direction for a test to be wrong in. A hidden conhost is now
reported for the record and judged by nothing.

  windows        - a VISIBLE console-class window owned by a descendant of the watched pid.
                   This is the thing the boss sees, and the only thing that fails a run.
  hiddenConsoles - conhost.exe processes in the tree, informational. Under the policy there
                   will usually be one per spawn, which is the policy working.

USAGE. Spawned by console_proof.mjs and by preflight's check 21:
    python console_watch.py --pid <server pid> [--seconds 20]
It prints one line, `WATCHING`, and then polls until it reads `stop` on stdin or the timeout
expires, at which point it prints one line of JSON and exits 0.
"""
import argparse
import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes

CONSOLE_CLASSES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS",
                   "PseudoConsoleWindow")
CONSOLE_IMAGES = ("conhost.exe",)

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def snapshot():
    """pid -> (parent pid, image name), via Toolhelp32 rather than WMI.

    WMI costs about 200 ms a call on this box, which is slower than the window being
    watched for. Toolhelp32 costs about 2 ms, which is what makes an 8 ms poll possible.
    """
    kernel32 = ctypes.windll.kernel32
    out = {}
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == -1:
        return out
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = kernel32.Process32First(handle, ctypes.byref(entry))
        while ok:
            out[int(entry.th32ProcessID)] = (
                int(entry.th32ParentProcessID),
                entry.szExeFile.decode("mbcs", "replace"))
            ok = kernel32.Process32Next(handle, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(handle)
    return out


def visible_consoles():
    """Every VISIBLE window of a console class, as a list of (pid, hwnd, class)."""
    user32 = ctypes.windll.user32
    found = []
    buf = ctypes.create_unicode_buffer(160)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        user32.GetClassNameW(hwnd, buf, 160)
        if buf.value in CONSOLE_CLASSES:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((int(pid.value), int(hwnd), buf.value))
        return True

    user32.EnumWindows(each, 0)
    return found


class Watch(object):
    def __init__(self, root):
        self.root = int(root)
        self.known = {}                       # accumulated pid -> (ppid, image)
        self.windows = []                     # hits attributed to our tree
        self.bystanders = []                  # hits belonging to somebody else
        self.consoles = {}                    # conhost pids in our tree
        self.polls = 0
        self.seen_windows = set()
        self.refresh()
        self.baseline = {(p, h) for p, h, _c in visible_consoles()}

    def refresh(self):
        self.known.update(snapshot())         # update, never replace: dead pids stay named

    def chain(self, pid):
        out, cur = [], int(pid)
        for _ in range(16):
            if cur not in self.known:
                out.append("?(%d)" % cur)
                break
            ppid, image = self.known[cur]
            out.append("%s(%d)" % (image, cur))
            if cur == self.root or not ppid or ppid == cur:
                break
            cur = ppid
        return out

    def ours(self, pid):
        cur = int(pid)
        for _ in range(16):
            if cur == self.root:
                return True
            if cur not in self.known:
                return False
            ppid = self.known[cur][0]
            if not ppid or ppid == cur:
                return False
            cur = ppid
        return False

    def poll(self, elapsed_ms):
        self.polls += 1
        for pid, hwnd, cls in visible_consoles():
            key = (pid, hwnd)
            if key in self.baseline or key in self.seen_windows:
                continue
            self.seen_windows.add(key)
            self.refresh()                    # only on a hit: this is the expensive call
            row = {"pid": pid, "class": cls, "atMs": round(elapsed_ms),
                   "chain": self.chain(pid)}
            (self.windows if self.ours(pid) else self.bystanders).append(row)

    def sweep_processes(self):
        self.refresh()
        for pid, (_ppid, image) in list(self.known.items()):
            if image.lower() in CONSOLE_IMAGES and pid not in self.consoles:
                if self.ours(pid):
                    self.consoles[pid] = {"pid": pid, "image": image,
                                          "chain": self.chain(pid)}

    def verdict(self):
        # `silent` is about the WINDOW and nothing else - see the note at the top of this
        # file for the A/B that took the hidden conhost out of the verdict.
        return {"root": self.root, "polls": self.polls,
                "windows": self.windows, "bystanders": self.bystanders,
                "hiddenConsoles": list(self.consoles.values()),
                "silent": not self.windows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    if sys.platform != "win32":
        print(json.dumps({"skipped": "not windows", "silent": True}))
        return 0

    watch = Watch(args.pid)
    stop = threading.Event()

    def listen():
        # A harness ends the watch by writing one line; the timeout is the backstop for a
        # harness that dies holding the pipe open. END OF INPUT IS NOT A STOP: a watcher
        # started with stdin closed - a shell redirect, or any spawn that does not bother
        # with a pipe - would otherwise return `polls: 0, silent: true` before it had
        # looked at anything even once, which is a green light for an unwatched desktop.
        try:
            for line in sys.stdin:
                if line.strip().lower() in ("stop", "q", "end"):
                    stop.set()
                    return
        except Exception:                                     # noqa: BLE001
            pass

    threading.Thread(target=listen, daemon=True).start()
    print("WATCHING", flush=True)

    started = time.monotonic()
    last_sweep = 0.0
    while not stop.is_set():
        elapsed = time.monotonic() - started
        if elapsed >= args.seconds:
            break
        watch.poll(elapsed * 1000.0)
        if elapsed - last_sweep > 0.25:
            watch.sweep_processes()
            last_sweep = elapsed
        time.sleep(0.008)
    watch.sweep_processes()
    print(json.dumps(watch.verdict()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
