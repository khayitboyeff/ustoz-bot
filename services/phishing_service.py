from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_URGENCY = ("darhol", "hozir", "oxirgi imkon", "hisob yopiladi", "urgent", "immediately", "act now", "срочно")
_CREDENTIALS = ("parol", "password", "otp", "tasdiqlash kodi", "pin kod", "cvv", "karta raqami")
_PRIZE = ("sovrin", "yutdingiz", "free prize", "you won", "bitcoin", "airdrop")
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly")


def _looks_private_host(host: str) -> bool:
    host = host.strip("[]")
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        lowered = host.casefold()
        return lowered in {"localhost", "metadata.google.internal"} or lowered.endswith(".local")


def analyze_message(text: str) -> dict:
    raw = (text or "").strip()
    if not raw or len(raw) > 4000:
        raise ValueError("Tahlil uchun 1–4000 belgilik matn yuboring.")
    lowered = raw.casefold()
    indicators: list[str] = []
    score = 0

    if any(word in lowered for word in _URGENCY):
        indicators.append("Shoshiltirish iboralari")
        score += 2
    if any(word in lowered for word in _CREDENTIALS):
        indicators.append("Parol yoki tasdiqlash kodi so‘ralishi")
        score += 3
    if any(word in lowered for word in _PRIZE):
        indicators.append("Kutilmagan sovrin yoki pul va’dasi")
        score += 2

    for match in _URL_RE.findall(raw):
        parsed = urlparse(match)
        host = (parsed.hostname or "").casefold()
        if not host:
            indicators.append("Noto‘g‘ri URL")
            score += 1
            continue
        if parsed.username or "@" in match.split("://", 1)[-1].split("/", 1)[0]:
            indicators.append("URL ichida foydalanuvchi qismi yoki @ belgisi")
            score += 3
        if _looks_private_host(host):
            indicators.append("Ichki yoki loopback manzil (so‘rov yuborilmadi)")
            score += 2
        if any(host == item or host.endswith("." + item) for item in _SHORTENERS):
            indicators.append("Qisqartirilgan havola — haqiqiy domen yashirin bo‘lishi mumkin")
            score += 2
        if parsed.scheme == "http":
            indicators.append("HTTP (shifrsiz) havola")
            score += 1
        if host.replace(".", "").isdigit() or ":" in host:
            indicators.append("IP manzilli havola")
            score += 2

    if score >= 5:
        level = "yuqori"
    elif score >= 2:
        level = "o‘rta"
    else:
        level = "past"

    advice = [
        "Havolani ochmang va parol yubormang.",
        "Jo‘natuvchini alohida, ishonchli kanal orqali tasdiqlang.",
        "Shubha bo‘lsa, tashkilot xavfsizlik jamoasiga xabar bering.",
    ]
    return {
        "level": level,
        "score": score,
        "indicators": indicators,
        "advice": advice,
        "fetched_url": False,
    }
