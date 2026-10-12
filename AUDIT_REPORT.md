# CyberUstozBot — Telegram-only security and feature audit

## Scope
This build intentionally has **no website, web admin dashboard, Flask server, or HTML privacy-policy site**. All user and admin interactions happen in Telegram. `web_admin.py`, `run_web_admin.bat`, `privacy-policy.html`, and the Flask dependency were removed.

## Added
- Four manual Premium plans: 1 month 15,000 UZS; 3 months 40,000 UZS; 6 months 70,000 UZS; 12 months 100,000 UZS.
- Manual card receipt flow. Receipt request is stored in SQLite, copied to configured admins, and reviewed via inline buttons. Only admins can approve/reject. A DB transaction and unique payment event prevent repeated approval from granting Premium twice.
- Referral milestones: 15 invited accounts → 30 days; 30 invited accounts → 90 days total (an additional 60 days if the 15-invite reward was already granted). Each milestone is recorded once. Referrals are attributed once and self-referrals are rejected by the existing referral logic.
- OSINT display order: Telegram, Instagram, GitHub; GitHub uses the public API and inconclusive API/network states are not reported as nonexistence.
- Configuration and documentation revised for Telegram-only use.

## Security notes
- Manual bank transfers are **not verified automatically**. Admin must compare the receipt against the bank/payment app before choosing the approval duration.
- Premium approval checks `ADMIN_IDS`, and review status is changed transactionally to prevent duplicate grants.
- Do not share `.env`, bot tokens, database, backups, logs, or user receipts.
- OSINT does not scrape Telegram/Instagram; it provides profile links and a GitHub public API status only.
- AI needs valid provider credentials. Do not send secrets in prompts.
- CTF remains an offline educational lab.

## Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: **99 passed** in the available test environment (Python 3.13; Telegram library source from the existing project archive was used for local tests).
- Live Telegram polling, AI provider requests, and real bank transfer verification were not performed; these require the owner's credentials and real services.
- Install dependencies from `requirements.txt` in the target Windows environment before launching the bot.
