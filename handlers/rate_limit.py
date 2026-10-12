from __future__ import annotations

import time
from collections import OrderedDict
from functools import wraps
from typing import Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

Handler = TypeVar("Handler", bound=Callable)
_MAX_ENTRIES = 20_000
_ENTRY_TTL_SECONDS = 3_600.0
_last_requests: OrderedDict[tuple[int, str], float] = OrderedDict()


def consume_rate_limit(user_id: int, scope: str, cooldown: float, now: float | None = None) -> bool:
    current_time = time.monotonic() if now is None else now
    key = (user_id, scope)
    last_request = _last_requests.get(key)
    if last_request is not None and current_time - last_request < cooldown:
        return True

    _last_requests[key] = current_time
    _last_requests.move_to_end(key)
    if len(_last_requests) > _MAX_ENTRIES:
        expired = [entry for entry, timestamp in _last_requests.items() if current_time - timestamp > _ENTRY_TTL_SECONDS]
        for entry in expired:
            _last_requests.pop(entry, None)
        while len(_last_requests) > _MAX_ENTRIES:
            _last_requests.popitem(last=False)
    return False


def rate_limited(scope: str, cooldown: float = 2.0) -> Callable[[Handler], Handler]:
    def decorate(handler: Handler) -> Handler:
        @wraps(handler)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = getattr(update, "effective_user", None)
            user_data = getattr(context, "user_data", None)
            if user_data is not None and scope not in {"text_message", "ip_command", "dns_command"}:
                user_data.pop("pending_lookup", None)
            if user is not None and consume_rate_limit(user.id, scope, cooldown):
                query = getattr(update, "callback_query", None)
                if query is not None:
                    await query.answer("Juda tez so‘rov yuborildi. Biroz kutib qayta urinib ko‘ring.")
                else:
                    message = getattr(update, "effective_message", None)
                    if message is not None:
                        await message.reply_text("Juda tez so‘rov yuborildi. Biroz kutib qayta urinib ko‘ring.")
                return None
            return await handler(update, context)

        return wrapped  # type: ignore[return-value]

    return decorate