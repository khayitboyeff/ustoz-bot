import pytest

flask = pytest.importorskip("flask")


def test_dashboard_requires_configuration(monkeypatch):
    import web_admin
    monkeypatch.setattr(web_admin, "WEB_ADMIN_USERNAME", "")
    client = web_admin.app.test_client()
    response = client.get("/login")
    assert response.status_code == 503


def test_login_form_has_csrf_and_dashboard_is_protected(monkeypatch):
    import re
    import web_admin
    monkeypatch.setattr(web_admin, "WEB_ADMIN_USERNAME", "test-admin")
    monkeypatch.setattr(web_admin, "WEB_ADMIN_PASSWORD", "test-password")
    monkeypatch.setattr(web_admin, "WEB_ADMIN_SECRET", "x" * 40)
    web_admin.app.config["SECRET_KEY"] = "x" * 40
    client = web_admin.app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match
    csrf = match.group(1).decode()
    denied = client.post("/login", data={"username": "test-admin", "password": "bad", "csrf_token": csrf})
    assert denied.status_code == 401
    response = client.get("/dashboard")
    assert response.status_code == 302
