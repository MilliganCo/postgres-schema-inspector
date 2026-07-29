"""Real SIGINT against installed ``pginspect`` entrypoint (POSIX only).

F-11 / C-14: stalled connect-test receives SIGINT → exit 130, no CommandResult JSON
on stdout.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.integration

_SKIP_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SIGINT process-group delivery for CLI entrypoint is POSIX-only; "
    "Windows Ctrl-C / GenerateConsoleCtrlEvent is not covered here (C-14 unit "
    "KeyboardInterrupt path remains covered in tests/unit/test_main_wrapper.py).",
)


@pytest.fixture
def stall_port() -> Iterator[int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = int(sock.getsockname()[1])
    stop = threading.Event()
    held: list[socket.socket] = []

    def _serve() -> None:
        sock.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
                held.append(conn)
            except TimeoutError:
                continue
            except OSError:
                break

    thread = threading.Thread(target=_serve, name="sigint-stall", daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=2)
        for conn in held:
            try:
                conn.close()
            except OSError:
                pass
        try:
            sock.close()
        except OSError:
            pass


@_SKIP_WINDOWS
def test_entrypoint_sigint_exits_130_without_json(stall_port: int) -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    # Point at stall server; connect will hang until SIGINT.
    cmd = [
        "pginspect",
        "connect-test",
        "--host",
        "127.0.0.1",
        "--port",
        str(stall_port),
        "--dbname",
        "postgres",
        "--user",
        "pginspect_test",
        "--connect-timeout",
        "30",
        "--format",
        "json",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    try:
        # Allow the child to enter connect().
        time.sleep(0.8)
        assert proc.poll() is None, "process exited before SIGINT"
        os.kill(proc.pid, signal.SIGINT)
        try:
            stdout_b, stderr_b = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_b, stderr_b = proc.communicate(timeout=5)
            pytest.fail("pginspect did not exit after SIGINT")
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 130, f"expected exit 130, got {proc.returncode}; stderr={stderr_b!r}"
    stdout = stdout_b.decode("utf-8", errors="replace")
    assert stdout.strip() == "", f"stdout must be empty on interrupt, got {stdout!r}"
    assert '"command"' not in stdout
    assert '"outcome"' not in stdout
