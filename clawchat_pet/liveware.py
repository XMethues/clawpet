"""Lifecycle management for the Liveware tunnel agent owned by clawchat-pet."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import IO


class LivewareAgentRunner:
    """Start one ``liveware agent`` process and stop only the process we own."""

    def __init__(self, hermes_home: Path | None = None) -> None:
        self.hermes_home = Path(
            hermes_home or os.environ.get("HERMES_HOME") or Path.home() / ".hermes"
        )
        self.binary = self.hermes_home / "clawchat" / "liveware" / "liveware"
        self.runtime_dir = self.hermes_home / "clawchat-pet"
        self.pid_file = self.runtime_dir / "liveware-agent.pid"
        self.log_file = self.hermes_home / "clawchat" / "liveware" / "agent.log"
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_handle: IO[bytes] | None = None
        self._lock = threading.Lock()

    def ensure_running(self) -> bool:
        """Start the agent unless this or the previous plugin process already did."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return False
            self._close_log()
            if not self.binary.is_file():
                return False

            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            previous_pid = self._read_pid_file()
            if previous_pid is not None and self._pid_is_liveware_agent(previous_pid):
                self._terminate_pid(previous_pid)

            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.log_file.open("ab", buffering=0)
            try:
                self._proc = subprocess.Popen(
                    [str(self.binary), "agent"],
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                )
            except Exception:
                self._proc = None
                self._close_log()
                raise
            self.pid_file.write_text(f"{self._proc.pid}\n", encoding="utf-8")
            return True

    def _read_pid_file(self) -> int | None:
        try:
            raw = self.pid_file.read_text(encoding="utf-8").strip()
            return int(raw)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            self.pid_file.unlink(missing_ok=True)
            return None

    @staticmethod
    def _pid_is_liveware_agent(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return False
        args = [part.decode(errors="replace") for part in cmdline.split(b"\0") if part]
        return bool(args and "liveware" in Path(args[0]).name.lower() and "agent" in args[1:])

    def _terminate_pid(self, pid: int) -> None:
        """Terminate only a PID that still identifies as ``liveware agent``."""
        if not self._pid_is_liveware_agent(pid):
            return
        os.kill(pid, signal.SIGTERM)

    def stop(self) -> None:
        """Stop the process spawned by this runner; never signal an external PID."""
        with self._lock:
            proc = self._proc
            self._proc = None
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            self.pid_file.unlink(missing_ok=True)
            self._close_log()

    def _close_log(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


_runner = LivewareAgentRunner()


def ensure_running() -> bool:
    return _runner.ensure_running()


def stop() -> None:
    _runner.stop()
