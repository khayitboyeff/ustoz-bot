from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

_env_values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}


def _get(name: str, default: str = "") -> str:
    """OS environment takes precedence over local .env configuration."""
    value = os.environ.get(name)
    if value is None:
        value = _env_values.get(name)
    return str(value if value is not None else default).strip()

BOT_TOKEN = (_get("BOT_TOKEN") or "").strip()
ADMIN_IDS = []
raw_admin_ids = (_get("ADMIN_IDS") or "").strip()
if raw_admin_ids:
    try:
        ADMIN_IDS = sorted({int(item.strip()) for item in raw_admin_ids.split(",") if item.strip()})
    except ValueError as exc:
        raise ValueError("ADMIN_IDS .env faylida vergul bilan ajratilgan butun sonlar bo‘lishi kerak.") from exc
    if any(admin_id <= 0 for admin_id in ADMIN_IDS):
        raise ValueError("ADMIN_IDS .env faylida faqat musbat Telegram ID qiymatlari bo‘lishi kerak.")

IPWHOIS_API_KEY = (_get("IPWHOIS_API_KEY") or "").strip()
PAYMENT_PROVIDER = (_get("PAYMENT_PROVIDER") or "none").strip().lower()
PAYMENT_PROVIDER_TOKEN = (_get("PAYMENT_PROVIDER_TOKEN") or "").strip()
PAYMENT_CURRENCY = (_get("PAYMENT_CURRENCY") or "").strip().upper()
raw_payment_amount = (_get("PAYMENT_AMOUNT_MINOR") or "").strip()
try:
    PAYMENT_AMOUNT_MINOR = int(raw_payment_amount) if raw_payment_amount else 0
except ValueError:
    PAYMENT_AMOUNT_MINOR = 0

LOG_LEVEL = (_get("LOG_LEVEL") or "INFO").strip() or "INFO"
DATABASE_PATH = (_get("DATABASE_PATH") or "").strip()
AI_API_KEY = (_get("AI_API_KEY") or "").strip()
AI_BASE_URL = (_get("AI_BASE_URL") or "https://api.openai.com/v1").strip()
AI_MODEL = (_get("AI_MODEL") or "").strip()
try:
    AI_TIMEOUT_SECONDS = int((_get("AI_TIMEOUT_SECONDS") or "20").strip() or "20")
except ValueError:
    AI_TIMEOUT_SECONDS = 20
try:
    AI_DAILY_LIMIT_FREE = int((_get("AI_DAILY_LIMIT_FREE") or "5").strip() or "5")
except ValueError:
    AI_DAILY_LIMIT_FREE = 5
try:
    AI_DAILY_LIMIT_PREMIUM = int((_get("AI_DAILY_LIMIT_PREMIUM") or "30").strip() or "30")
except ValueError:
    AI_DAILY_LIMIT_PREMIUM = 30
PAYMENT_TITLE = (_get("PAYMENT_TITLE") or "CyberUstozBot Premium 30 kun").strip()
PAYMENT_DESCRIPTION = (_get("PAYMENT_DESCRIPTION") or "30 kunlik o‘quv Premium obunasi").strip()

PAYMENT_CARD_NUMBER = (_get("PAYMENT_CARD_NUMBER") or "").strip()
PAYMENT_CARD_HOLDER = (_get("PAYMENT_CARD_HOLDER") or "").strip()
PAYMENT_CARD_BANK = (_get("PAYMENT_CARD_BANK") or "").strip()
PAYMENT_CARD_INSTRUCTIONS = (_get("PAYMENT_CARD_INSTRUCTIONS") or "Kartaga to‘lov qiling, chekni botga yuboring. Admin tekshirgach obuna faollashadi.").strip()
