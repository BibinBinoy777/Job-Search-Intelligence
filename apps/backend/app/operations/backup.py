"""Native coherent backup and isolated restore. Never restores over an existing database."""

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.session import engine
from app.modules.resumes.storage import PrivateStorage


class BackupError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native(binary_dir, command, database_url, *args, output=None):
    url = make_url(database_url)
    environment = {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database or "",
        "PGCONNECT_TIMEOUT": "5",
    }
    exe = Path(binary_dir) / (command + (".exe" if os.name == "nt" else ""))
    try:
        result = subprocess.run(
            [str(exe), *map(str, args)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError("native_tool_unavailable_or_timed_out") from None
    if result.returncode:
        raise BackupError(command + "_failed")
    return result.stdout


def tables_snapshot(conn, tables=None):
    names = (
        tables
        or conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        ).all()
    )
    result = {}
    for name in names:
        # Table names come only from PostgreSQL metadata, never user-provided SQL.
        table = conn.dialect.identifier_preparer.quote(name)
        rows = conn.execute(text("SELECT * FROM " + table)).mappings().all()
        canonical = sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in rows)
        result[name] = {"rows": len(rows), "sha256": digest(json.dumps(canonical).encode())}
    return result


def create_backup(destination, binary_dir, database_engine=engine, storage=None):
    storage = storage or PrivateStorage()
    destination = Path(destination).resolve()
    project = Path(__file__).resolve().parents[4]
    if destination.is_relative_to(project) or destination.is_relative_to(storage.root):
        raise BackupError("backup_must_be_outside_source_and_document_root")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = destination / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex)
    target.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        with database_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            with conn.begin():
                # Wait at most five seconds rather than silently backing up live,
                # conflicting document mutations. These locks block writes until
                # both the native snapshot dump and referenced files are copied.
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                names = conn.scalars(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                    )
                ).all()
                quoted = ",".join(conn.dialect.identifier_preparer.quote(n) for n in names)
                conn.execute(text("LOCK TABLE " + quoted + " IN SHARE MODE"))
                snapshot = conn.scalar(text("SELECT pg_export_snapshot()"))
                before = tables_snapshot(conn, names)
                refs = conn.execute(
                    text(
                        "SELECT storage_ref, checksum, size_bytes FROM resume_versions ORDER BY storage_ref"
                    )
                ).all()
                objects = {}
                for ref, checksum, size in refs:
                    content = storage.read(ref)
                    if len(content) != size or digest(content) != checksum:
                        raise BackupError("document_missing_or_checksum_mismatch")
                    path = target / "documents" / ref
                    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    path.write_bytes(content)
                    objects[ref] = {"sha256": checksum, "bytes": size}
                dump = target / "database.dump"
                native(
                    binary_dir,
                    "pg_dump",
                    database_engine.url,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot=" + snapshot,
                    "--file=" + str(dump),
                )
                native(binary_dir, "pg_restore", database_engine.url, "--list", dump)
                report = {
                    "format": "jsi-recovery-1",
                    "backup_id": target.name,
                    "created_at": datetime.now(UTC).isoformat(),
                    "database": database_engine.url.database,
                    "postgres_version": conn.scalar(text("SHOW server_version")),
                    "migration": conn.scalar(text("SELECT version_num FROM alembic_version")),
                    "database_sha256": digest(dump.read_bytes()),
                    "tables": before,
                    "documents": objects,
                    "encrypted": False,
                    "consistency": "exported PostgreSQL snapshot with write-blocking table locks and referenced document copies",
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "restore_verified": False,
                }
                (target / "manifest.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
        return target
    except Exception:
        (target / "FAILED").write_text("Backup incomplete; do not restore this set.")
        raise


def verify_backup(target):
    target = Path(target).resolve()
    if (target / "FAILED").exists():
        raise BackupError("incomplete_backup")
    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if manifest["format"] != "jsi-recovery-1" or manifest["backup_id"] != target.name:
            raise BackupError("backup_identity_mismatch")
        if digest((target / "database.dump").read_bytes()) != manifest["database_sha256"]:
            raise BackupError("database_checksum_mismatch")
        storage = PrivateStorage()
        storage.root = target / "documents"
        actual = set(
            p.relative_to(storage.root).as_posix() for p in storage.root.rglob("*") if p.is_file()
        )
        if actual != set(manifest["documents"]):
            raise BackupError("document_inventory_mismatch")
        for ref, expected in manifest["documents"].items():
            data = storage.read(ref)
            if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
                raise BackupError("document_checksum_mismatch")
        return manifest
    except (KeyError, ValueError, OSError):
        raise BackupError("backup_manifest_or_file_invalid") from None


def restore_test(target, binary_dir, admin_engine=engine, storage_destination=None):
    manifest = verify_backup(target)
    target = Path(target).resolve()
    name = "jsi_restore_" + uuid4().hex + "_restore_test"
    storage_destination = Path(
        storage_destination or target.parent / (name + "-documents")
    ).resolve()
    if storage_destination.is_relative_to(Path(__file__).resolve().parents[4]):
        raise BackupError("restore_storage_must_be_outside_source_and_web_roots")
    if storage_destination.exists():
        raise BackupError("restore_storage_must_not_exist")
    started = time.monotonic()
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text('CREATE DATABASE "' + name + '"'))
    url = admin_engine.url.set(database=name)
    restored = create_engine(url)
    try:
        native(
            binary_dir,
            "pg_restore",
            url,
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            "--dbname=" + name,
            target / "database.dump",
        )
        storage_destination.mkdir(mode=0o700)
        for ref in manifest["documents"]:
            path = storage_destination / ref
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(target / "documents" / ref, path)
        with restored.connect() as conn:
            if tables_snapshot(conn) != manifest["tables"]:
                raise BackupError("restored_database_values_mismatch")
            refs = conn.execute(
                text("SELECT storage_ref,checksum,size_bytes FROM resume_versions")
            ).all()
            if set(r[0] for r in refs) != set(manifest["documents"]):
                raise BackupError("restored_document_references_mismatch")
            for ref, checksum, size in refs:
                data = (storage_destination / ref).read_bytes()
                if digest(data) != checksum or len(data) != size:
                    raise BackupError("restored_document_content_mismatch")
        result = {
            "backup_id": manifest["backup_id"],
            "status": "verified",
            "database": name,
            "documents": len(refs),
            "table_count": len(manifest["tables"]),
            "duration_seconds": round(time.monotonic() - started, 3),
            "all_original_values_preserved": True,
        }
        (target / "restore-verification.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        return result
    finally:
        restored.dispose()


def retention_plan(directory, recent=7, weekly=4, monthly=12, apply=False):
    directory = Path(directory).resolve()
    if recent < 1 or weekly < 0 or monthly < 0:
        raise BackupError("invalid_retention")
    candidates = []
    for path in directory.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            m = verify_backup(path)
            proof = json.loads((path / "restore-verification.json").read_text())
            if proof.get("backup_id") != m["backup_id"] or proof.get("status") != "verified":
                continue
            candidates.append((m["created_at"], path))
        except (BackupError, OSError, ValueError):
            continue
    candidates.sort(reverse=True)
    keep = {p for _, p in candidates[:recent]}
    for mode, limit in [("weekly", weekly), ("monthly", monthly)]:
        periods = set()
        for stamp, path in candidates:
            day = datetime.fromisoformat(stamp)
            key = day.strftime("%G-%V" if mode == "weekly" else "%Y-%m")
            if key not in periods and len(periods) < limit:
                periods.add(key)
                keep.add(path)
    removed = []
    for _, path in candidates:
        if path in keep:
            continue
        # Refuse any computed deletion outside this explicit backup root.
        resolved = path.resolve()
        if resolved.parent != directory or any(p.is_symlink() for p in path.rglob("*")):
            raise BackupError("unsafe_retention_path")
        if apply:
            shutil.rmtree(resolved)
        removed.append(path.name)
    return {
        "apply": apply,
        "eligible_backup_sets": removed,
        "kept_verified": len(keep),
        "unverified_sets": "retained; manual inspection required",
    }
