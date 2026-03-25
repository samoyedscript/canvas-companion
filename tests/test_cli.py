"""Tests for cli.py using Typer's CliRunner."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from canvas_companion.cli import app

runner = CliRunner()


def test_doctor_missing_config(monkeypatch):
    """Doctor should fail gracefully when config is missing."""
    monkeypatch.delenv("CC_CANVAS_BASE_URL", raising=False)
    monkeypatch.delenv("CC_CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CC_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CC_TELEGRAM_CHAT_ID", raising=False)

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Canvas LMS monitor" in result.stdout
