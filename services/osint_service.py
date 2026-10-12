from __future__ import annotations

import re
from typing import Any

import requests


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,50}$")


def check_public_username(username: str) -> list[dict[str, Any]]:
    """Return three public profile entry points in the requested order.

    Telegram/Instagram are linked directly rather than scraped. GitHub is queried
    only through its public API; failures are labelled inconclusive, not as absence.
    """
    cleaned = (username or "").strip()
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    if not cleaned or not USERNAME_RE.fullmatch(cleaned):
        return []
    results: list[dict[str, Any]] = [
        {"platform": "Telegram", "status": "profilni ochib tekshiring", "url": f"https://t.me/{cleaned}"},
        {"platform": "Instagram", "status": "profilni ochib tekshiring", "url": f"https://www.instagram.com/{cleaned}/"},
    ]
    github_url = f"https://github.com/{cleaned}"
    try:
        response = requests.get(
            f"https://api.github.com/users/{cleaned}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CyberUstozBot-OSINT"},
            timeout=(3, 5),
            allow_redirects=False,
        )
        if response.status_code == 200:
            status = "ochiq profil topildi"
        elif response.status_code == 404:
            status = "GitHub profili topilmadi"
        elif response.status_code == 403:
            status = "API limitiga yetildi; keyinroq tekshiring"
        else:
            status = "tekshirib bo‘lmadi"
    except requests.RequestException:
        status = "tarmoq/API mavjud emas; profil havolasini qo‘lda tekshiring"
    results.append({"platform": "GitHub", "status": status, "url": github_url})
    return results


def safe_domain_research(domain: str) -> dict[str, str]:
    cleaned = (domain or "").strip().lower().rstrip(".")
    if not cleaned:
        return {
            "domain": "",
            "whois": "tekshirib bo‘lmadi",
            "dns": "tekshirib bo‘lmadi",
            "website": "tekshirib bo‘lmadi",
        }

    return {
        "domain": cleaned,
        "whois": "Rasmiy WHOIS ma’lumotlari ochiq ma’lumotlar ro‘yxati orqali tekshirilishi mumkin.",
        "dns": "A, AAAA, MX va NS yozuvlari DNS so‘rov orqali tekshiriladi.",
        "website": f"https://{cleaned}",
    }
