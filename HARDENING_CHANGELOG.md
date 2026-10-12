# CyberUstozBot hardening changelog

## 2026-10-10

1. **Stars payload authenticity:** HMAC-SHA256 signature keyed by BOT_TOKEN prevents users from altering plan/user fields in an invoice payload without detection.
2. **Nonce validation:** invoice payload includes a full 32-character random hex nonce.
3. **Pre-checkout verification:** signed payload, owner Telegram ID, tariff, XTR currency and exact amount are checked before approval.
4. **Successful-payment verification:** the same validations run again before granting Premium.
5. **Invoice spam control:** per-user 5-second cooldown added to Stars invoice creation.
6. **Payment idempotency:** existing transactional charge-ID duplicate protection retained.
7. **Operational security guidance:** documented secrets handling, manual receipt verification, limiter scope, and production test requirements.

Validation: Python compileall passed. Full automated tests could not be executed in this environment because `python-telegram-bot` is not installed. No live Telegram payment test was performed.
