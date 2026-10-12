from __future__ import annotations

from content.ctf_challenges import CTF_CHALLENGES
from database.features import get_ctf_challenge, list_ctf_challenges, seed_ctf_challenges, submit_ctf_answer, ctf_progress, use_ctf_hint
from services.premium_service import has_active_premium


def ensure_ctf_seeded() -> None:
    existing = list_ctf_challenges()
    by_slug = {item["slug"]: item for item in existing}
    needs_seed = len(existing) < len(CTF_CHALLENGES) or any(
        slug not in by_slug or int(by_slug[slug].get("is_premium", 0)) != int(bool(source.get("is_premium", False)))
        for source in CTF_CHALLENGES
        for slug in [source["slug"]]
    )
    if needs_seed:
        seed_ctf_challenges(CTF_CHALLENGES)


def challenges() -> list[dict]:
    ensure_ctf_seeded()
    return list_ctf_challenges()


def challenge(challenge_id: int) -> dict | None:
    ensure_ctf_seeded()
    return get_ctf_challenge(challenge_id)


def submit(telegram_id: int, challenge_id: int, answer: str) -> dict:
    ensure_ctf_seeded()
    item = get_ctf_challenge(challenge_id)
    if item is None:
        return {"ok": False, "reason": "missing"}
    if item.get("is_premium") and not has_active_premium(telegram_id):
        return {"ok": False, "reason": "premium"}
    return submit_ctf_answer(telegram_id, challenge_id, answer)


def hint(telegram_id: int, challenge_id: int) -> dict | None:
    ensure_ctf_seeded()
    item = get_ctf_challenge(challenge_id)
    if item is None:
        return None
    if item.get("is_premium") and not has_active_premium(telegram_id):
        return {"locked": True}
    return use_ctf_hint(telegram_id, challenge_id)


def progress(telegram_id: int) -> dict:
    ensure_ctf_seeded()
    return ctf_progress(telegram_id)
