from __future__ import annotations

import csv
import hmac
import io
import logging
import secrets
import time
from functools import wraps

from flask import Flask, Response, abort, redirect, render_template_string, request, session, url_for

from config import (
    WEB_ADMIN_PASSWORD,
    WEB_ADMIN_SECRET,
    WEB_ADMIN_USERNAME,
    WEB_DASHBOARD_HOST,
    WEB_DASHBOARD_PORT,
)
from database.db import DB_PATH, get_admin_stats, get_connection, init_db

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=WEB_ADMIN_SECRET or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=WEB_DASHBOARD_HOST not in {"127.0.0.1", "localhost", "::1"},
    PERMANENT_SESSION_LIFETIME=1800,
    MAX_CONTENT_LENGTH=16 * 1024,
)

LOGIN_TEMPLATE = r"""
<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CyberUstozBot · Admin login</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#07111f;color:#eaf2ff;font:16px system-ui}
.card{width:min(420px,92vw);padding:30px;border:1px solid #233b58;border-radius:20px;background:#0d1b2d;box-shadow:0 20px 80px #0006}
h1{margin:0 0 8px;font-size:25px}.muted{color:#91a8c4;font-size:14px}label{display:block;margin:16px 0 7px}
input{width:100%;padding:12px;border:1px solid #2b4665;border-radius:10px;background:#07111f;color:#fff}
button{margin-top:20px;width:100%;padding:12px;border:0;border-radius:10px;background:#38bdf8;color:#042033;font-weight:700;cursor:pointer}
.err{color:#fca5a5;background:#451a24;padding:10px;border-radius:9px}.mark{color:#38bdf8;font-weight:800;letter-spacing:.1em}
</style></head><body><main class="card"><div class="mark">CYBERUSTOZBOT</div><h1>Admin dashboard</h1>
<p class="muted">Xavfsiz boshqaruv paneliga kirish</p>{% if error %}<p class="err">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('login') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Admin username</label><input name="username" autocomplete="username" required maxlength="128">
<label>Parol</label><input name="password" type="password" autocomplete="current-password" required maxlength="256>
<button type="submit">Kirish</button></form></main></body></html>
"""

DASHBOARD_TEMPLATE = r"""
<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CyberUstozBot · Admin</title><style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0d1b2d;--line:#233b58;--muted:#91a8c4;--blue:#38bdf8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#eaf2ff;font:15px system-ui}a{color:var(--blue);text-decoration:none}
header{display:flex;align-items:center;justify-content:space-between;padding:22px max(20px,calc((100vw - 1200px)/2));border-bottom:1px solid var(--line);background:#0a1728}
.wrap{max-width:1200px;margin:auto;padding:24px 18px}.brand{font-weight:800;letter-spacing:.08em;color:var(--blue)}.muted{color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;margin:20px 0}
.card,section{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:18px}.num{font-size:28px;font-weight:800;margin-top:6px}
.grid{display:grid;grid-template-columns:1.3fr 1fr;gap:16px}@media(max-width:850px){.grid{grid-template-columns:1fr}}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:0 0 14px}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.table-wrap{overflow:auto}input{padding:10px;background:#07111f;border:1px solid var(--line);border-radius:8px;color:#fff}
button,.btn{border:0;border-radius:8px;background:var(--blue);color:#052033;font-weight:700;padding:10px 13px;cursor:pointer}
.search{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px}.search input{flex:1;min-width:180px}
.pill{display:inline-block;padding:4px 8px;border-radius:20px;background:#12364a;color:#7dd3fc}.foot{margin-top:22px;color:var(--muted);font-size:12px}
</style></head><body>
<header><div><div class="brand">CYBERUSTOZBOT</div><div class="muted">Admin dashboard · Read-only operations</div></div>
<form method="post" action="{{ url_for('logout') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button>Chiqish</button></form></header>
<main class="wrap"><h1>Umumiy ko‘rsatkichlar</h1><p class="muted">Ma’lumotlar loyihaning SQLite bazasidan olinadi.</p>
<div class="cards">
<div class="card"><div class="muted">Foydalanuvchilar</div><div class="num">{{ stats.total_users }}</div></div>
<div class="card"><div class="muted">Faol Premium</div><div class="num">{{ stats.premium_users }}</div></div>
<div class="card"><div class="muted">Tugallangan quiz</div><div class="num">{{ stats.total_quizzes }}</div></div>
<div class="card"><div class="muted">Javoblar</div><div class="num">{{ stats.total_answers }}</div></div>
<div class="card"><div class="muted">Tugallangan darslar</div><div class="num">{{ stats.lessons_completed }}</div></div>
<div class="card"><div class="muted">O‘rtacha ball</div><div class="num">{{ "%.1f"|format(stats.avg_test_score) }}</div></div>
</div>
<div class="grid"><section><h2>Foydalanuvchilar</h2>
<form class="search" method="get"><input name="q" value="{{ query }}" placeholder="ID, username yoki ism bo‘yicha qidirish" maxlength="100"><button>Qidirish</button><a class="btn" href="{{ url_for('export_users') }}">CSV eksport</a></form>
<div class="table-wrap"><table><thead><tr><th>Telegram ID</th><th>Foydalanuvchi</th><th>Ro‘yxatdan o‘tgan</th><th>Quizlar</th><th>Premium</th></tr></thead><tbody>
{% for u in users %}<tr><td>{{ u.telegram_id }}</td><td>{{ (u.first_name or '') }} {{ (u.last_name or '') }}<br><span class="muted">@{{ u.username or 'username yo‘q' }}</span></td>
<td>{{ u.created_at or '—' }}</td><td>{{ u.quiz_attempts or 0 }}</td><td>{% if u.is_premium %}<span class="pill">Premium</span>{% else %}Bepul{% endif %}</td></tr>
{% else %}<tr><td colspan="5">Foydalanuvchi topilmadi.</td></tr>{% endfor %}</tbody></table></div>
<p class="muted">Sahifa {{ page }} · Jami mos natija: {{ total }}</p>
<div class="search">{% if page > 1 %}<a class="btn" href="{{ url_for('dashboard',q=query,page=page-1) }}">← Oldingi</a>{% endif %}
{% if page * per_page < total %}<a class="btn" href="{{ url_for('dashboard',q=query,page=page+1) }}">Keyingi →</a>{% endif %}</div>
</section><section><h2>Oxirgi admin hodisalari</h2><div class="table-wrap"><table><thead><tr><th>Vaqt</th><th>Admin</th><th>Amal</th><th>Nishon</th></tr></thead><tbody>
{% for row in audit %}<tr><td>{{ row.created_at }}</td><td>{{ row.actor_admin_id }}</td><td>{{ row.action }}</td><td>{{ row.target_user_id }}</td></tr>{% else %}<tr><td colspan="4">Audit yozuvlari hali mavjud emas.</td></tr>{% endfor %}
</tbody></table></div><p class="muted">Panel faqat ko‘rish va eksport qilish uchun. Premium yoki foydalanuvchi ma’lumotlarini bu yerdan o‘zgartirib bo‘lmaydi.</p></section></div>
<div class="foot">Database: {{ db_name }} · Maxfiy ma’lumotlar yashirilgan · CyberUstozBot</div></main></body></html>
"""

_login_attempts: dict[str, list[float]] = {}


def _configured() -> bool:
    return bool(
        WEB_ADMIN_USERNAME
        and WEB_ADMIN_PASSWORD
        and len(WEB_ADMIN_SECRET) >= 32
    )


def _csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _verify_csrf() -> None:
    supplied = request.form.get("csrf_token", "")
    expected = session.get("_csrf", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        abort(400, description="CSRF tekshiruvi muvaffaqiyatsiz.")


def _login_limited() -> bool:
    now = time.time()
    history = [t for t in _login_attempts.get(request.remote_addr or "unknown", []) if now - t < 300]
    _login_attempts[request.remote_addr or "unknown"] = history
    return len(history) >= 8


def _record_login_failure() -> None:
    key = request.remote_addr or "unknown"
    _login_attempts.setdefault(key, []).append(time.time())


def _require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("web_admin_authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/healthz", methods=["GET"])
def healthz():
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "database": "ok"}, 200
    except Exception:
        logger.exception("Dashboard health check failed.")
        return {"status": "error", "database": "unavailable"}, 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if not _configured():
        return "Dashboard sozlanmagan. WEB_ADMIN_USERNAME, WEB_ADMIN_PASSWORD va kamida 32 belgili WEB_ADMIN_SECRET kiriting.", 503
    if request.method == "GET":
        return render_template_string(LOGIN_TEMPLATE, csrf=_csrf_token(), error="")
    _verify_csrf()
    if _login_limited():
        return render_template_string(LOGIN_TEMPLATE, csrf=_csrf_token(), error="Juda ko‘p urinish. 5 daqiqadan keyin qayta urinib ko‘ring."), 429
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if hmac.compare_digest(username.encode(), WEB_ADMIN_USERNAME.encode()) and hmac.compare_digest(password.encode(), WEB_ADMIN_PASSWORD.encode()):
        session.clear()
        session["web_admin_authenticated"] = True
        session.permanent = True
        session["_csrf"] = secrets.token_urlsafe(32)
        _login_attempts.pop(request.remote_addr or "unknown", None)
        destination = request.args.get("next", "")
        if not destination.startswith("/") or destination.startswith("//"):
            destination = url_for("dashboard")
        return redirect(destination)
    _record_login_failure()
    logger.warning("Dashboard login failed from %s", request.remote_addr or "unknown")
    return render_template_string(LOGIN_TEMPLATE, csrf=_csrf_token(), error="Login yoki parol noto‘g‘ri."), 401


@app.route("/logout", methods=["POST"])
@_require_login
def logout():
    _verify_csrf()
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
@_require_login
def dashboard():
    try:
        stats = get_admin_stats()
        page = max(1, min(int(request.args.get("page", "1")), 1_000_000))
    except (ValueError, TypeError):
        abort(400)
    per_page = 25
    query = (request.args.get("q", "") or "").strip()[:100]
    where = ""
    params: list[object] = []
    if query:
        where = "WHERE CAST(telegram_id AS TEXT) LIKE ? OR COALESCE(username,'') LIKE ? OR COALESCE(first_name,'') LIKE ? OR COALESCE(last_name,'') LIKE ?"
        wildcard = f"%{query}%"
        params = [wildcard] * 4
    with get_connection() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM users {where}", params).fetchone()[0])
        rows = conn.execute(
            f"SELECT telegram_id, username, first_name, last_name, created_at, quiz_attempts, is_premium FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, per_page, (page - 1) * per_page],
        ).fetchall()
        try:
            audit = conn.execute("SELECT created_at, actor_admin_id, action, target_user_id FROM admin_audit_log ORDER BY id DESC LIMIT 20").fetchall()
        except Exception:
            audit = []
    return render_template_string(
        DASHBOARD_TEMPLATE, stats=stats, users=[dict(r) for r in rows],
        audit=[dict(r) for r in audit], query=query, page=page,
        per_page=per_page, total=total, csrf=_csrf_token(), db_name=DB_PATH.name,
    )


@app.route("/export/users.csv", methods=["GET"])
@_require_login
def export_users():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["telegram_id", "username", "first_name", "last_name", "created_at", "quiz_attempts", "is_premium"])
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT telegram_id, username, first_name, last_name, created_at, quiz_attempts, is_premium FROM users ORDER BY created_at DESC"
        ).fetchall()
        for row in rows:
            values = [row[k] for k in ("telegram_id", "username", "first_name", "last_name", "created_at", "quiz_attempts", "is_premium")]
            # Avoid spreadsheet formula execution from user-controlled text fields.
            safe_values = [
                ("'" + value) if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"} else value
                for value in values
            ]
            writer.writerow(safe_values)
    return Response(
        "\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cyberustozbot-users.csv"},
    )


def main() -> None:
    if not _configured():
        raise SystemExit(
            "Dashboard konfiguratsiyasi yetishmaydi: WEB_ADMIN_USERNAME, WEB_ADMIN_PASSWORD va "
            "WEB_ADMIN_SECRET (kamida 32 belgi) ni .env ga kiriting."
        )
    init_db()
    # Do not expose this development server to the public internet. Use a production WSGI server behind TLS for remote access.
    app.run(host=WEB_DASHBOARD_HOST, port=WEB_DASHBOARD_PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
