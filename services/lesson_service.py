from __future__ import annotations

from database.db import get_connection

CUSTOM_ID_OFFSET = 10_000


def list_custom_lessons() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, body, video_url, video_file_id FROM custom_lessons WHERE is_active=1 ORDER BY id"
        ).fetchall()
    return [
        {"id": CUSTOM_ID_OFFSET + int(row["id"]), "title": row["title"], "text": row["body"],
         "video_url": row["video_url"], "video_file_id": row["video_file_id"], "is_custom": True}
        for row in rows
    ]


def create_custom_lesson(title: str, body: str, video_url: str | None, admin_id: int) -> int:
    title = (title or "").strip()
    body = (body or "").strip()
    video_url = (video_url or "").strip() or None
    if not 3 <= len(title) <= 120:
        raise ValueError("Dars nomi 3–120 belgi bo‘lishi kerak.")
    if not 20 <= len(body) <= 100_000:
        raise ValueError("Dars matni 20–100 000 belgi bo‘lishi kerak.")
    if video_url and (len(video_url) > 500 or not video_url.startswith(("https://", "http://"))):
        raise ValueError("Video havolasi http:// yoki https:// bilan boshlanishi kerak.")
    if type(admin_id) is not int or admin_id <= 0:
        raise ValueError("Admin ID noto‘g‘ri.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO custom_lessons(title, body, video_url, created_by) VALUES (?, ?, ?, ?)",
            (title, body, video_url, admin_id),
        )
        conn.commit()
        return CUSTOM_ID_OFFSET + int(cur.lastrowid)


def attach_video_file(lesson_id: int, file_id: str) -> bool:
    if type(lesson_id) is not int or lesson_id < CUSTOM_ID_OFFSET:
        raise ValueError("Maxsus dars ID noto‘g‘ri.")
    if not isinstance(file_id, str) or not file_id:
        raise ValueError("Video fayli noto‘g‘ri.")
    raw_id = lesson_id - CUSTOM_ID_OFFSET
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE custom_lessons SET video_file_id=? WHERE id=? AND is_active=1",
            (file_id, raw_id),
        )
        conn.commit()
        return cur.rowcount > 0
