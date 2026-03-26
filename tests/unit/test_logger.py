"""Unit tests for src/logger.py."""

import logging

from src.logger import CredentialMaskingFilter, get_logger, LOG_FORMAT


class TestCredentialMaskingFilter:
    def test_masks_github_token(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret123")
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="token is ghp_secret123", args=None, exc_info=None,
        )
        f.filter(record)
        assert "ghp_secret123" not in record.msg
        assert "***" in record.msg

    def test_masks_multiple_credentials(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "gh_abc")
        monkeypatch.setenv("LLM_API_KEY", "sk-xyz")
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="gh_abc and sk-xyz leaked", args=None, exc_info=None,
        )
        f.filter(record)
        assert "gh_abc" not in record.msg
        assert "sk-xyz" not in record.msg

    def test_no_masking_when_env_unset(self):
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="nothing to mask", args=None, exc_info=None,
        )
        f.filter(record)
        assert record.msg == "nothing to mask"

    def test_masks_with_format_args(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "secret")
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="value=%s", args=("secret",), exc_info=None,
        )
        f.filter(record)
        assert "secret" not in record.msg
        assert "***" in record.msg


class TestGetLogger:
    def test_returns_logger_with_name(self):
        logger = get_logger("mymodule")
        assert logger.name == "mymodule"

    def test_default_level_is_info(self):
        logger = get_logger("test.default_level")
        assert logger.level == logging.INFO

    def test_respects_log_level_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        logger = get_logger("test.debug_level")
        assert logger.level == logging.DEBUG

    def test_handler_has_correct_format(self):
        logger = get_logger("test.format_check")
        assert len(logger.handlers) >= 1
        handler = logger.handlers[0]
        assert handler.formatter._fmt == LOG_FORMAT

    def test_handler_has_masking_filter(self):
        logger = get_logger("test.filter_check")
        handler = logger.handlers[0]
        filters = handler.filters
        assert any(isinstance(f, CredentialMaskingFilter) for f in filters)
