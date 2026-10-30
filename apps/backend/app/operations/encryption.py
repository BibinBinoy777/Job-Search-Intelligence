"""Optional Windows DPAPI envelope. Keys are managed by the Windows user profile."""

import ctypes
import io
import os
import zipfile
from pathlib import Path

from app.operations.backup import BackupError, verify_backup


def protect(data, decrypt=False):
    if os.name != "nt":
        raise BackupError("dpapi_requires_windows")
    if len(data) > 256 * 1024 * 1024:
        raise BackupError("encryption_size_limit")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    function = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    result = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(out))
    if not result:
        raise BackupError("dpapi_operation_failed")
    try:
        return ctypes.string_at(out.data, out.length)
    finally:
        ctypes.windll.kernel32.LocalFree(out.data)


def encrypt_backup(target, output):
    target = Path(target).resolve()
    verify_backup(target)
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(target):
        raise BackupError("encrypted_output_must_be_new_and_outside_set")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in target.rglob("*"):
            if path.is_symlink():
                raise BackupError("backup_symlink_rejected")
            if path.is_file():
                archive.write(path, target.name + "/" + path.relative_to(target).as_posix())
    output.write_bytes(b"JSI-DPAPI-1\n" + protect(stream.getvalue()))
    return {
        "encrypted": True,
        "scope": "same Windows user/profile; not a portable off-host recovery guarantee",
        "plaintext_original_retained": True,
    }


def decrypt_backup(encrypted, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise BackupError("decrypt_destination_must_not_exist")
    data = Path(encrypted).read_bytes()
    prefix = b"JSI-DPAPI-1\n"
    if not data.startswith(prefix):
        raise BackupError("unknown_envelope")
    with zipfile.ZipFile(io.BytesIO(protect(data[len(prefix) :], decrypt=True))) as archive:
        if sum(i.file_size for i in archive.infolist()) > 256 * 1024 * 1024:
            raise BackupError("encryption_size_limit")
        for item in archive.infolist():
            path = destination / item.filename
            if not path.resolve().is_relative_to(destination) or "\\" in item.filename:
                raise BackupError("archive_path_rejected")
        archive.extractall(destination)
    sets = list(destination.iterdir())
    if len(sets) != 1:
        raise BackupError("ambiguous_backup_set")
    verify_backup(sets[0])
    return sets[0]
