from pathlib import PurePath
from typing import Protocol

MIMES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeError(Exception):
    def __init__(self, code):
        self.code = code


MESSAGES = {
    "unsupported_file": "Upload a PDF or DOCX with the matching content type.",
    "invalid_filename": "Use a plain filename of up to 180 characters, without path separators.",
    "invalid_signature": "The file content does not match its declared PDF/DOCX format.",
    "invalid_document": "The document is malformed or unsupported. Export a fresh PDF or DOCX.",
    "password_protected": "Remove document password protection before uploading.",
    "active_document": "Embedded active content, attachments or macros are not supported. Export a plain resume.",
    "archive_limit": "The DOCX archive exceeds safe expansion or structure limits.",
    "document_limit": "The document exceeds page, section or extracted-content limits. Upload a shorter resume.",
    "ocr_required": "No usable text layer was found in this image-based PDF. OCR is required; OCR was not run.",
    "empty_text": "No useful text was extracted. Upload a document containing selectable professional text.",
    "parser_timeout": "Document processing exceeded the time limit. Export a simpler document and retry.",
    "parser_failed": "The document parser could not finish. Export a fresh document or retry.",
    "parser_busy": "Document processing capacity is busy. Retry shortly.",
    "isolation_unavailable": "Document processing isolation is unavailable on this server.",
    "storage_unavailable": "Private document storage is temporarily unavailable. Retry later.",
}


def file_type(filename, mime, content):
    if not filename or len(filename) > 180 or any(ord(c) < 32 or c in "/\\:" for c in filename):
        raise ResumeError("invalid_filename")
    kind = PurePath(filename).suffix.lower().lstrip(".")
    if kind not in MIMES or mime.split(";", 1)[0].lower() != MIMES[kind]:
        raise ResumeError("unsupported_file")
    if not content or not content.startswith(b"%PDF-" if kind == "pdf" else b"PK\x03\x04"):
        raise ResumeError("invalid_signature")
    return kind


class MalwareScanner(Protocol):
    def scan(self, content: bytes, kind: str) -> str: ...


class NoScanner:
    def scan(self, content, kind):
        return "not_configured"


scanner: MalwareScanner = NoScanner()
