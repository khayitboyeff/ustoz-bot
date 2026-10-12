from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import database.db as db

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"


def _validate_database(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Backup fayli mavjud emas yoki xavfsiz emas.")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
    try:
        check = conn.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            raise ValueError("SQLite backup yaxlitligi tekshiruvidan o‘tmadi.")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"users", "quiz_questions", "quiz_runs"}.issubset(tables):
            raise ValueError("SQLite fayli KiberUstoz bazasi schema’siga mos emas.")
    except sqlite3.DatabaseError as exc:
        raise ValueError("Backup yaroqli SQLite ma’lumotlar bazasi emas.") from exc
    finally:
        conn.close()


def create_database_backup(backup_dir: Path | None = None) -> Path:
    destination_dir = (backup_dir or BACKUP_DIR).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    if not db.DB_PATH.is_file():
        raise FileNotFoundError("Asosiy ma’lumotlar bazasi topilmadi.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"cyberlearn-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    temporary = destination.with_suffix(".sqlite3.tmp")
    source = sqlite3.connect(db.DB_PATH, timeout=10)
    target = sqlite3.connect(temporary, timeout=10)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    _validate_database(temporary)
    os.replace(temporary, destination)
    return destination


def restore_database_backup(filename: str, backup_dir: Path | None = None) -> dict[str, Path]:
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".sqlite3"):
        raise ValueError("Faqat backups papkasidagi .sqlite3 fayl nomini kiriting.")
    source_dir = (backup_dir or BACKUP_DIR).resolve()
    candidate = source_dir / filename
    if candidate.is_symlink():
        raise ValueError("Symlink orqali backup tiklashga ruxsat yo‘q.")
    backup = candidate.resolve()
    if backup.parent != source_dir:
        raise ValueError("Backup fayli ruxsat etilgan papkadan tashqarida.")
    _validate_database(backup)

    safety_backup = create_database_backup(source_dir)
    target = db.DB_PATH.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.restore")
    source_conn = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True, timeout=10)
    target_conn = sqlite3.connect(temporary, timeout=10)
    try:
        source_conn.backup(target_conn)
        target_conn.commit()
    finally:
        target_conn.close()
        source_conn.close()
    _validate_database(temporary)
    os.replace(temporary, target)
    return {"restored": target, "safety_backup": safety_backup}
