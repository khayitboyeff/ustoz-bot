from __future__ import annotations

from datetime import date, timedelta

import database.db as db


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "community.sqlite3")
    db.init_db()
    db.ensure_user(1001, username="inviter", first_name="Inviter")
    db.ensure_user(1002, username="invitee", first_name="Invitee")


def test_referral_is_unique_and_blocks_self_referral(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    code = db.ensure_referral_code(1001)
    assert code == db.ensure_referral_code(1001)
    assert db.register_referral(1001, code) is False
    assert db.register_referral(1002, code) is True
    assert db.register_referral(1002, code) is False
    assert db.get_referral_stats(1001)["invited"] == 1
    assert db.get_referral_stats(1002)["invited"] == 0


def test_streak_counts_once_per_day_and_resets_after_gap(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    first = date(2026, 10, 1)
    assert db.record_user_activity(1001, first.isoformat())["streak"] == 1
    duplicate = db.record_user_activity(1001, first.isoformat())
    assert duplicate["streak"] == 1
    assert duplicate["already_counted"] is True
    assert db.record_user_activity(1001, (first + timedelta(days=1)).isoformat())["streak"] == 2
    assert db.record_user_activity(1001, (first + timedelta(days=3)).isoformat())["streak"] == 1
    assert db.get_user_activity(1001)["total_active_days"] == 3


def test_subscription_settings_and_channel_upsert(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    assert db.is_subscription_required() is False
    db.add_required_channel("-100123", "cyber_news", "https://t.me/cyber_news", "Cyber News")
    db.add_required_channel("-100123", "cyber_news", "https://t.me/cyber_news", "Cyber News Updated")
    channels = db.get_active_required_channels()
    assert len(channels) == 1
    assert channels[0]["title"] == "Cyber News Updated"
    db.set_subscription_required(True)
    assert db.is_subscription_required() is True
    assert db.remove_required_channel("@cyber_news") is True
    assert db.get_active_required_channels() == []
