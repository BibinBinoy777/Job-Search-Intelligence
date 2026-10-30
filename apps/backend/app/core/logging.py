import json
import logging
import re
from datetime import UTC, datetime


class SafeOperationalFormatter(logging.Formatter):
    def format(self, record):
        # Explicit metadata only. Never serialize exception objects, arbitrary
        # request payloads, interpolated source text or SQL parameter messages.
        event = str(record.msg).split(" ", 1)[0]
        if not re.fullmatch(r"[a-z_]{1,80}", event):
            event = "component_event"
        value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "component": record.name,
            "event": event,
        }
        for key in ["error_category", "task_id", "run_id", "correlation_id", "resource_id"]:
            item = getattr(record, key, None)
            if item is not None and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", str(item)):
                value[key] = item
        return json.dumps(value)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeOperationalFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
