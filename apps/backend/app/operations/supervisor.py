"""Session-local supervisor for the existing worker; not an installed OS service."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def write_state(path, **data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"observed_at": datetime.now(UTC).isoformat(), **data}), encoding="utf-8"
    )
    temporary.replace(path)


def supervise(directory):
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stop = directory / "worker.stop"
    state = directory / "worker-state.json"
    with (directory / "supervisor.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if stop.exists():
            raise RuntimeError("Remove the previous stop marker explicitly before starting")
        restarts = 0
        while not stop.exists():
            started = time.monotonic()
            with (directory / "worker-errors.log").open("ab"):
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "app.ingestion.cli",
                        "worker",
                        "--schedule",
                        "--runtime-state",
                        str(directory / "worker-record.json"),
                        "--stop-file",
                        str(stop),
                    ],
                    cwd=Path(__file__).resolve().parents[2],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    while process.poll() is None:
                        write_state(
                            state,
                            supervisor_pid=os.getpid(),
                            worker_pid=process.pid,
                            status="stopping" if stop.exists() else "running_process",
                            restarts=restarts,
                            health_note="Process presence alone is not worker health; inspect database heartbeat",
                        )
                        time.sleep(1)
                except KeyboardInterrupt:
                    stop.touch()
                    try:
                        process.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        write_state(
                            state, status="stop_timeout", worker_pid=process.pid, restarts=restarts
                        )
                        raise RuntimeError(
                            "Worker did not drain; inspect active task and process before stopping manually"
                        ) from None
            if stop.exists():
                break
            restarts += 1
            delay = min(2 ** min(restarts, 5), 30)
            write_state(
                state,
                status="restart_backoff",
                exit_code=process.returncode,
                restarts=restarts,
                backoff_seconds=delay,
            )
            for _ in range(delay):
                if stop.exists():
                    break
                time.sleep(1)
            if time.monotonic() - started > 300:
                restarts = 0
        write_state(state, status="stopped", restarts=restarts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    supervise(args.directory)
