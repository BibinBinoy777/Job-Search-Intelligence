import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter
from sqlalchemy import text

from app.api.automation import automation_status, operator
from app.api.dependencies import DB, CurrentUser
from app.modules.resumes.storage import PrivateStorage

router = APIRouter(prefix="/api/v1/operations", tags=["Local operations"])


@router.get("/health")
def health(db: DB, user: CurrentUser):
    operator(user)
    result = automation_status(db, user)
    runtime = Path(__file__).resolve().parents[4] / ".local" / "operations"
    for name in ["worker-record", "worker-state", "backup-state"]:
        try:
            data = json.loads((runtime / (name + ".json")).read_text(encoding="utf-8"))
            age = (datetime.now(UTC) - datetime.fromisoformat(data["observed_at"])).total_seconds()
            result[name] = {
                **data,
                "freshness": "recent" if age <= 45 else "stale",
                "age_seconds": round(age, 1),
            }
        except (OSError, ValueError, KeyError):
            result[name] = {"status": "not_recorded"}
    db.execute(text("SELECT 1"))
    result.update(
        {
            "backend": "available",
            "database": "available",
            "frontend": "not_independently_verified",
            "malware_scanning": "not_configured",
            "backup": "inspect_local_verified_backup_manifest",
            "production_supervision": "not_verified",
        }
    )
    try:
        storage = PrivateStorage()
        if not storage.root.exists():
            result["storage"] = "not_initialized"
        else:
            with NamedTemporaryFile(dir=storage.root, prefix="health-", delete=True) as probe:
                probe.write(b"jsi-health")
                probe.flush()
                os.fsync(probe.fileno())
            result["storage"] = "readable_writable"
    except (OSError, ValueError):
        result["storage"] = "unavailable"
    return result
