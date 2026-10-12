from __future__ import annotations

import database.db as db
from services.lesson_service import create_custom_lesson, list_custom_lessons


def test_custom_lesson_accepts_long_text(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "long-lessons.sqlite3")
    db.init_db()
    body = ("Uzun dars matni. " * 300)  # well over the previous 3,000-character limit
    lesson_id = create_custom_lesson("Uzun kiberxavfsizlik darsi", body, None, 123456)
    lesson = next(item for item in list_custom_lessons() if item["id"] == lesson_id)
    assert len(lesson["text"]) > 3000
    assert lesson["text"] == body.strip()
