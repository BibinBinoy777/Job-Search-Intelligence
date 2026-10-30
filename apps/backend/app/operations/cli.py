"""Explicit local administrative operations; never resets or seeds application data."""

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.operations.accounts import delete_account, issue_local_recovery
from app.operations.backup import create_backup, restore_test, verify_backup


def backup_status(**values):
    from app.operations.supervisor import write_state

    runtime = Path(__file__).resolve().parents[4] / ".local" / "operations"
    runtime.mkdir(parents=True, exist_ok=True)
    write_state(runtime / "backup-state.json", **values)


def main():
    p = argparse.ArgumentParser()
    commands = p.add_subparsers(dest="command", required=True)
    b = commands.add_parser("backup")
    b.add_argument("--destination", type=Path, required=True)
    b.add_argument("--pg-bin", type=Path, required=True)
    r = commands.add_parser("restore-test")
    r.add_argument("--backup", type=Path, required=True)
    r.add_argument("--pg-bin", type=Path, required=True)
    v = commands.add_parser("verify-backup")
    v.add_argument("--backup", type=Path, required=True)
    a = commands.add_parser("issue-local-recovery")
    a.add_argument("--email", required=True)
    a.add_argument("--output", type=Path, required=True)
    d = commands.add_parser("retry-account-deletion")
    d.add_argument("--user-id", required=True)
    e = commands.add_parser("encrypt-backup")
    e.add_argument("--backup", type=Path, required=True)
    e.add_argument("--output", type=Path, required=True)
    e = commands.add_parser("decrypt-backup")
    e.add_argument("--envelope", type=Path, required=True)
    e.add_argument("--destination", type=Path, required=True)
    e = commands.add_parser("retention")
    e.add_argument("--directory", type=Path, required=True)
    e.add_argument("--recent", type=int, default=7)
    e.add_argument("--weekly", type=int, default=4)
    e.add_argument("--monthly", type=int, default=12)
    e.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if args.command == "retention":
        from app.operations.backup import retention_plan

        print(
            json.dumps(
                retention_plan(args.directory, args.recent, args.weekly, args.monthly, args.apply)
            )
        )
    elif args.command == "encrypt-backup":
        from app.operations.encryption import encrypt_backup

        print(json.dumps(encrypt_backup(args.backup, args.output)))
    elif args.command == "decrypt-backup":
        from app.operations.encryption import decrypt_backup

        target = decrypt_backup(args.envelope, args.destination)
        print(json.dumps({"status": "decrypted_integrity_verified", "backup_id": target.name}))
    elif args.command == "backup":
        target = create_backup(args.destination, args.pg_bin)
        backup_status(backup_id=target.name, status="created_not_restore_verified", encrypted=False)
        print(
            json.dumps(
                {
                    "backup_set": target.name,
                    "status": "created_not_restore_verified",
                    "encrypted": False,
                }
            )
        )
    elif args.command == "restore-test":
        result = restore_test(args.backup, args.pg_bin)
        backup_status(
            backup_id=result["backup_id"],
            status="restore_verified",
            documents=result["documents"],
            duration_seconds=result["duration_seconds"],
            encrypted=False,
        )
        print(json.dumps(result))
    elif args.command == "verify-backup":
        m = verify_backup(args.backup)
        print(
            json.dumps(
                {
                    "backup_id": m["backup_id"],
                    "integrity": "passed",
                    "restore_verified": (args.backup / "restore-verification.json").exists(),
                    "encrypted": False,
                }
            )
        )
    elif args.command == "issue-local-recovery":
        project = Path(__file__).resolve().parents[4]
        output = args.output.resolve()
        if output.is_relative_to(project):
            raise RuntimeError("Recovery file must be outside source/web roots")
        with SessionLocal.begin() as db:
            token = issue_local_recovery(db, args.email)
            with output.open("x", encoding="utf-8") as stream:
                stream.write(token)
            output.chmod(0o600)
        print(
            "Local recovery credential saved privately. Expires in 20 minutes; single use. Do not share or log it."
        )
    else:
        from app.db.models import User

        with SessionLocal() as db:
            user = db.get(User, args.user_id)
            if user and not user.deletion_pending:
                raise RuntimeError("Only already confirmed pending deletion may be retried")
            result = delete_account(db, args.user_id)
            db.commit()
            print(json.dumps(result))


if __name__ == "__main__":
    main()
