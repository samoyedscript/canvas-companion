"""Tests for config.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from canvas_companion.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("CC_CANVAS_BASE_URL", "https://canvas.example.com")
    monkeypatch.setenv("CC_CANVAS_API_TOKEN", "tok123")
    monkeypatch.setenv("CC_TELEGRAM_BOT_TOKEN", "bot:xyz")
    monkeypatch.setenv("CC_TELEGRAM_CHAT_ID", "999")

    s = Settings()  # type: ignore[call-arg]
    assert s.canvas_base_url == "https://canvas.example.com"
    assert s.canvas_api_token.get_secret_value() == "tok123"
    assert s.sync_interval_minutes == 30  # default
    assert s.log_level == "INFO"  # default


def test_settings_missing_required_raises(monkeypatch):
    # Clear any CC_ vars
    for key in list(monkeypatch._env_setattr if hasattr(monkeypatch, '_env_setattr') else []):
        pass
    monkeypatch.delenv("CC_CANVAS_BASE_URL", raising=False)
    monkeypatch.delenv("CC_CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CC_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CC_TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_custom_defaults(monkeypatch):
    monkeypatch.setenv("CC_CANVAS_BASE_URL", "https://canvas.example.com")
    monkeypatch.setenv("CC_CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CC_TELEGRAM_BOT_TOKEN", "bot:x")
    monkeypatch.setenv("CC_TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("CC_SYNC_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("CC_LOG_LEVEL", "DEBUG")

    s = Settings()  # type: ignore[call-arg]
    assert s.sync_interval_minutes == 60
    assert s.log_level == "DEBUG"


def test_gemini_settings_optional(monkeypatch):
    """Gemini settings should be optional with sensible defaults."""
    monkeypatch.setenv("CC_CANVAS_BASE_URL", "https://canvas.example.com")
    monkeypatch.setenv("CC_CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CC_TELEGRAM_BOT_TOKEN", "bot:x")
    monkeypatch.setenv("CC_TELEGRAM_CHAT_ID", "1")

    s = Settings()  # type: ignore[call-arg]
    assert s.gemini_api_key is None
    assert s.gemini_model == "gemini-2.5-flash"


def test_gemini_settings_loaded(monkeypatch):
    """Gemini settings should load when provided."""
    monkeypatch.setenv("CC_CANVAS_BASE_URL", "https://canvas.example.com")
    monkeypatch.setenv("CC_CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CC_TELEGRAM_BOT_TOKEN", "bot:x")
    monkeypatch.setenv("CC_TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("CC_GEMINI_API_KEY", "gemini-key-123")
    monkeypatch.setenv("CC_GEMINI_MODEL", "gemini-2.5-pro")

    s = Settings()  # type: ignore[call-arg]
    assert s.gemini_api_key.get_secret_value() == "gemini-key-123"
    assert s.gemini_model == "gemini-2.5-pro"
