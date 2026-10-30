import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from app.core.config import settings
from app.modules.resumes.validation import ResumeError

EXTRACTOR_VERSION = "resume-deterministic-1.0"
gate = threading.BoundedSemaphore(2)


def parse_document(content, kind, validate_only=False):
    if not gate.acquire(blocking=False):
        raise ResumeError("parser_busy")
    try:
        request = {
            "content": base64.b64encode(content).decode(),
            "kind": kind,
            "validate_only": validate_only,
            "max_pages": settings.resume_max_pages,
            "max_chars": settings.resume_max_text_chars,
            "max_sections": settings.resume_max_sections,
        }
        try:
            with tempfile.TemporaryDirectory(prefix="jsi-parser-") as temporary:
                backend = str(Path(__file__).resolve().parents[3])
                bootstrap = (
                    "import sys,socket,runpy;sys.path.insert(0," + repr(backend) + ");"
                    "socket.socket=lambda *a,**k:(_ for _ in ()).throw(PermissionError('network_disabled'));"
                    "socket.create_connection=socket.socket;"
                    "runpy.run_module('app.modules.resumes.worker',run_name='__main__')"
                )
                environment = {
                    key: os.environ[key] for key in ["SYSTEMROOT", "WINDIR"] if key in os.environ
                }
                environment.update(
                    {"TEMP": temporary, "TMP": temporary, "PYTHONIOENCODING": "utf-8"}
                )
                result = subprocess.run(
                    [sys.executable, "-I", "-c", bootstrap],
                    input=json.dumps(request).encode(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=settings.resume_parser_timeout_seconds,
                    cwd=temporary,
                    env=environment,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            raise ResumeError("parser_timeout") from None
        except OSError:
            raise ResumeError("parser_failed") from None
        if result.returncode or len(result.stdout) > 4 * settings.resume_max_text_chars + 1000000:
            raise ResumeError("parser_failed")
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise ResumeError("parser_failed") from None
        if response.get("error"):
            raise ResumeError(response["error"])
        return response
    finally:
        gate.release()
