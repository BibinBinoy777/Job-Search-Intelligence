import os
import re
from pathlib import Path

from app.core.config import settings


class PrivateStorage:
    """Private filesystem adapter. API callers must establish ownership first."""

    def __init__(self):
        self.root = settings.resume_storage_root.expanduser().resolve()
        frontend = Path(__file__).resolve().parents[4] / "frontend"
        project = Path(__file__).resolve().parents[5]
        if (
            self.root.is_relative_to(frontend)
            or self.root == project
            or self.root.is_relative_to(project / "dist")
            or self.root.is_relative_to(project / "public")
        ):
            raise ValueError("Private resume storage must be outside web roots")

    def path(self, ref):
        if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f-]{36}\.blob", ref):
            raise ValueError("Invalid private object reference")
        raw = self.root / ref
        if (
            raw.parent.is_symlink()
            or raw.is_symlink()
            or not raw.resolve().is_relative_to(self.root)
        ):
            raise ValueError("Invalid private object path")
        return raw

    def write(self, ref, content):
        path = self.path(ref)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # O_EXCL never silently overwrites a prior uploaded version.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def read(self, ref):
        path = self.path(ref)
        with path.open("rb") as stream:
            content = stream.read(settings.resume_max_bytes + 1)
        if len(content) > settings.resume_max_bytes:
            raise ValueError("Private object exceeds configured size")
        return content

    def delete(self, ref):
        self.path(ref).unlink(missing_ok=True)
