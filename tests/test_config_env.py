from __future__ import annotations

import config


def test_environment_variable_overrides_dotenv(monkeypatch):
    monkeypatch.setitem(config._env_values, "BOT_TOKEN", "dotenv-value")
    monkeypatch.setenv("BOT_TOKEN", "environment-value")
    assert config._get("BOT_TOKEN") == "environment-value"


def test_dotenv_is_fallback_when_environment_missing(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setitem(config._env_values, "BOT_TOKEN", "dotenv-value")
    assert config._get("BOT_TOKEN") == "dotenv-value"


def test_missing_config_returns_default(monkeypatch):
    monkeypatch.delenv("MISSING_CYBERUSTOZ_SETTING", raising=False)
    assert config._get("MISSING_CYBERUSTOZ_SETTING", "fallback") == "fallback"
