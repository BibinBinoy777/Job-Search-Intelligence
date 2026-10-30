import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.operations.supervisor import write_state

worker_id = str(uuid4())
started = datetime.now(UTC).isoformat()


def record(**changes):
    configured = os.environ.get("JSI_WORKER_STATE_PATH")
    if not configured:
        return
    path = Path(configured)
    value = {}
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("worker_id") == worker_id:
            value = old
    except (OSError, ValueError):
        pass
    value.update({"worker_id": worker_id, "pid": os.getpid(), "started_at": started, **changes})
    write_state(path, **{k: v for k, v in value.items() if k != "observed_at"})
