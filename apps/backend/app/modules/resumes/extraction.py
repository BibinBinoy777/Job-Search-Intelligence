import base64
import json
import subprocess
import sys
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
            result = subprocess.run(
                [sys.executable, "-m", "app.modules.resumes.worker"],
                input=json.dumps(request).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=settings.resume_parser_timeout_seconds,
                cwd=Path(__file__).resolve().parents[3],
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
