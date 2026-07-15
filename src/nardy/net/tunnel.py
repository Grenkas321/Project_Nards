"""Auto-tunnel via Pinggy for internet play without manual port forwarding.

ngrok's free tier now requires a verified credit card for TCP endpoints
(ERR_NGROK_8013), which defeats the point of a zero-friction "just host and
share a code" flow. Pinggy offers free, no-signup TCP tunnels over plain SSH
— and every supported OS already ships an SSH client, so there is nothing to
install. Free tunnels expire after 60 minutes; hosting again just gets a new
address.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

_ADDR_RE = re.compile(r"tcp://([a-zA-Z0-9.\-]+):(\d+)")
_tunnel_processes: list[subprocess.Popen] = []


def _ssh_candidates() -> list[str]:
    """SSH clients to try, most-compatible first.

    Windows' bundled OpenSSH (System32) silently produces NO session output
    for `-R` reverse tunnels when run without a console/pty — the Pinggy
    banner with the address never arrives and the tunnel looks hung. Git for
    Windows ships an ssh that works fine through pipes, so prefer it.
    """
    candidates: list[str] = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            candidates.append(os.path.join(base, "Git", "usr", "bin", "ssh.exe"))
    from_path = shutil.which("ssh")
    if from_path:
        candidates.append(from_path)
    seen: set[str] = set()
    result = []
    for c in candidates:
        c_norm = os.path.normcase(c)
        if c_norm not in seen and os.path.isfile(c):
            seen.add(c_norm)
            result.append(c)
    return result


def is_ssh_available() -> bool:
    """Check whether any usable ssh client is present."""
    return bool(_ssh_candidates())


def start_tunnel(port: int = 8765, timeout: float = 30.0) -> tuple[str | None, str | None]:
    """Start a free Pinggy SSH TCP tunnel to ``localhost:port``.

    Returns ``(address, error)`` where address is ``"host:port"`` reachable
    from the public internet, valid for up to 60 minutes. Tries each ssh
    candidate in turn until one yields a tunnel address.
    """
    candidates = _ssh_candidates()
    if not candidates:
        return None, "ssh not found — install Git for Windows or OpenSSH."

    last_error = "Tunnel failed."
    for ssh in candidates:
        addr, last_error = _start_tunnel_with(ssh, port, timeout)
        if addr:
            return addr, None
    return None, last_error


def _start_tunnel_with(ssh: str, port: int, timeout: float) -> tuple[str | None, str | None]:
    """Try one ssh binary; return (address, error)."""
    # A real temp file, not NUL//dev/null: Git-for-Windows ssh runs in a
    # MSYS environment where "NUL" is treated as a regular relative path
    # and litters the working directory with a known_hosts file named NUL.
    import tempfile
    known_hosts = os.path.join(tempfile.gettempdir(), "nardy_known_hosts")
    creation = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        process = subprocess.Popen(
            [
                ssh, "-p", "443",
                "-o", "StrictHostKeyChecking=no",
                "-o", f"UserKnownHostsFile={known_hosts}",
                f"-R0:localhost:{port}", "tcp@a.pinggy.io",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True, bufsize=1, creationflags=creation,
        )
    except Exception as e:
        return None, str(e)

    _tunnel_processes.append(process)
    lines: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=_reader, daemon=True).start()

    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.terminate()
            return None, "Timed out waiting for tunnel address."
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            process.terminate()
            return None, "Timed out waiting for tunnel address."
        if line is None:
            return None, "ssh exited: " + "".join(seen)[-300:]
        seen.append(line)
        match = _ADDR_RE.search(line)
        if match:
            return f"{match.group(1)}:{match.group(2)}", None


def parse_tunnel_address(addr: str) -> tuple[str, int]:
    """Parse 'host:port' into (host, port), tolerating pasted extras.

    Grandparents paste creatively: strip whitespace, a 'tcp://' prefix, and
    trailing slashes before splitting.
    """
    addr = addr.strip().removeprefix("tcp://").rstrip("/")
    if ":" in addr:
        host, port_str = addr.rsplit(":", 1)
        try:
            return host, int(port_str)
        except ValueError:
            return host, 8765
    return addr, 8765
