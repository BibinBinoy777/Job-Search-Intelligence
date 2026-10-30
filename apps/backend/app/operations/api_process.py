"""Uvicorn controlled stop-file wrapper; SIGINT/shutdown still supported."""

import sys
import threading
import time
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    marker = Path(sys.argv[1])
    port = int(sys.argv[2])
    server = uvicorn.Server(
        uvicorn.Config("app.main:app", host="127.0.0.1", port=port, access_log=False)
    )

    def monitor():
        while not marker.exists():
            time.sleep(0.5)
        server.should_exit = True

    threading.Thread(target=monitor, daemon=True).start()
    server.run()
