"""Parser child process. Document contents never enter command arguments/logs."""

import base64
import ctypes
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import PurePosixPath

from app.modules.resumes.validation import ResumeError

_job_handle = None


def memory_limit():
    global _job_handle
    limit = 512 * 1024 * 1024
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        return
    from ctypes import wintypes as w

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", w.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", w.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", w.DWORD),
            ("SchedulingClass", w.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in [
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            ]
        ]

    class EXT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC),
            ("IoInfo", IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    _job_handle = kernel.CreateJobObjectW(None, None)
    info = EXT()
    info.BasicLimitInformation.LimitFlags = 0x100
    info.ProcessMemoryLimit = limit
    if (
        not _job_handle
        or not kernel.SetInformationJobObject(
            _job_handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        )
        or not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess())
    ):
        raise ResumeError("isolation_unavailable")


def parse(content, kind, limits, validate_only=False):
    from defusedxml.ElementTree import fromstring

    segments = []
    total = 0

    def add(text, page=None, part=None):
        nonlocal total
        text = text.replace("\x00", "").strip()
        if not text:
            return
        total += len(text)
        if total > limits["max_chars"] or len(segments) >= limits["max_sections"]:
            raise ResumeError("document_limit")
        segments.append({"id": len(segments), "text": text, "page": page, "part": part})

    if kind == "pdf":
        from pypdf import PdfReader, filters

        filters.ZLIB_MAX_OUTPUT_LENGTH = 8 * 1024 * 1024
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ResumeError("password_protected")
        root = reader.trailer["/Root"]

        def resolved(value):
            return value.get_object() if hasattr(value, "get_object") else value

        names = resolved(root.get("/Names", {}))
        if (
            "/OpenAction" in root
            or "/AA" in root
            or "/JavaScript" in names
            or "/EmbeddedFiles" in names
            or "/XFA" in resolved(root.get("/AcroForm", {}))
        ):
            raise ResumeError("active_document")
        if not reader.pages or len(reader.pages) > limits["max_pages"]:
            raise ResumeError("document_limit")
        images = False
        for number, page in enumerate(reader.pages, 1):
            if "/AA" in page:
                raise ResumeError("active_document")
            for annotation in page.get("/Annots", []):
                action = resolved(annotation.get_object().get("/A", {}))
                if action.get("/S") in {"/JavaScript", "/Launch"}:
                    raise ResumeError("active_document")
            if validate_only:
                continue
            objects = resolved(resolved(page.get("/Resources", {})).get("/XObject", {}))
            images = images or any(
                value.get_object().get("/Subtype") == "/Image" for value in objects.values()
            )
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > 8 * 1024 * 1024:
                raise ResumeError("document_limit")
            add(page.extract_text() or "", page=number, part="page")
        if not validate_only and not segments:
            raise ResumeError("ocr_required" if images else "empty_text")
        pages = len(reader.pages)
    else:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > 200
                or len({entry.filename for entry in entries}) != len(entries)
                or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024
            ):
                raise ResumeError("archive_limit")
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in entry.filename
                    or ":" in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or entry.flag_bits & 1
                    or entry.file_size > max(1, entry.compress_size) * 100
                ):
                    raise ResumeError("archive_limit")
                if "vbaproject" in entry.filename.lower() or entry.filename.lower().startswith(
                    ("word/embeddings/", "word/activex/")
                ):
                    raise ResumeError("active_document")
            if (
                "[Content_Types].xml" not in archive.namelist()
                or "word/document.xml" not in archive.namelist()
            ):
                raise ResumeError("invalid_document")
            types = archive.read("[Content_Types].xml")
            fromstring(types, forbid_dtd=True, forbid_entities=True, forbid_external=True)
            if b"macroEnabled" in types:
                raise ResumeError("active_document")
            for name in archive.namelist():
                if name.endswith(".rels"):
                    links = fromstring(
                        archive.read(name),
                        forbid_dtd=True,
                        forbid_entities=True,
                        forbid_external=True,
                    )
                    if any(
                        item.get("TargetMode") == "External"
                        and not item.get("Type", "").endswith("/hyperlink")
                        for item in links
                    ):
                        raise ResumeError("active_document")
            for name in sorted(
                n
                for n in archive.namelist()
                if n == "word/document.xml"
                or n.startswith(("word/header", "word/footer"))
                and n.endswith(".xml")
            ):
                document = fromstring(
                    archive.read(name), forbid_dtd=True, forbid_entities=True, forbid_external=True
                )
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                if name == "word/document.xml" and document.tag != ns + "document":
                    raise ResumeError("invalid_document")
                if validate_only:
                    continue
                for paragraph in document.iter(ns + "p"):

                    def text_nodes(node):
                        if node.tag in {ns + "del", ns + "instrText"}:
                            return ""
                        if node.tag == ns + "t":
                            return node.text or ""
                        if node.tag in {ns + "tab", ns + "br"}:
                            return " "
                        return "".join(text_nodes(child) for child in node)

                    add(
                        text_nodes(paragraph),
                        part="body/table paragraph"
                        if name == "word/document.xml"
                        else "header/footer paragraph",
                    )
        pages = None
        if not validate_only and not segments:
            raise ResumeError("empty_text")
    return {
        "segments": segments,
        "quality": {
            "text_chars": total,
            "segments": len(segments),
            "pages": pages,
            "ocr_performed": False,
            "parser_memory_limit_bytes": 512 * 1024 * 1024,
        },
    }


def main():
    try:
        memory_limit()
        raw = sys.stdin.buffer.read(15 * 1024 * 1024)
        request = json.loads(raw)
        result = parse(
            base64.b64decode(request["content"], validate=True),
            request["kind"],
            request,
            request["validate_only"],
        )
    except ResumeError as exc:
        result = {"error": exc.code}
    except Exception:
        result = {"error": "invalid_document"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
