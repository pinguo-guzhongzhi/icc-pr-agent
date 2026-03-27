"""Unit tests for custom exception classes."""

import pytest

from src.exceptions import (
    PRReviewError,
    UnknownPlatformError,
    CredentialMissingError,
    PlatformAPIError,
    TemplateNotFoundError,
    AIModelError,
    CommentWriteBackError,
    EmptyDiffError,
    AllFilesExcludedError,
    ExcludeConfigError,
    SymbolIndexError,
    SubAgentTimeoutError,
    TokenBudgetExceededError,
)


ALL_EXCEPTIONS = [
    UnknownPlatformError,
    CredentialMissingError,
    PlatformAPIError,
    TemplateNotFoundError,
    AIModelError,
    CommentWriteBackError,
    EmptyDiffError,
    AllFilesExcludedError,
    ExcludeConfigError,
    SymbolIndexError,
    SubAgentTimeoutError,
]


class TestExceptionHierarchy:
    """All custom exceptions inherit from PRReviewError."""

    @pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
    def test_inherits_from_base(self, exc_cls):
        assert issubclass(exc_cls, PRReviewError)

    @pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
    def test_inherits_from_exception(self, exc_cls):
        assert issubclass(exc_cls, Exception)


class TestExceptionMessage:
    """Each exception accepts and preserves a message."""

    @pytest.mark.parametrize("exc_cls", [PRReviewError] + ALL_EXCEPTIONS)
    def test_message_preserved(self, exc_cls):
        msg = "something went wrong"
        err = exc_cls(msg)
        assert str(err) == msg

    @pytest.mark.parametrize("exc_cls", [PRReviewError] + ALL_EXCEPTIONS)
    def test_can_be_raised_and_caught(self, exc_cls):
        with pytest.raises(exc_cls, match="test error"):
            raise exc_cls("test error")

    @pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
    def test_caught_by_base_class(self, exc_cls):
        with pytest.raises(PRReviewError):
            raise exc_cls("caught by base")


class TestExceptionDocstrings:
    """Each exception has a descriptive docstring."""

    @pytest.mark.parametrize("exc_cls", [PRReviewError] + ALL_EXCEPTIONS)
    def test_has_docstring(self, exc_cls):
        assert exc_cls.__doc__ is not None
        assert len(exc_cls.__doc__.strip()) > 0


class TestTokenBudgetExceededError:
    """TokenBudgetExceededError carries budget and used attributes."""

    def test_inherits_from_base(self):
        assert issubclass(TokenBudgetExceededError, PRReviewError)

    def test_attributes(self):
        err = TokenBudgetExceededError(budget=100000, used=120000)
        assert err.budget == 100000
        assert err.used == 120000
        assert "100000" in str(err)
        assert "120000" in str(err)

    def test_custom_message(self):
        err = TokenBudgetExceededError(budget=50000, used=60000, message="自定义熔断")
        assert str(err) == "自定义熔断"
        assert err.budget == 50000

    def test_caught_by_base_class(self):
        with pytest.raises(PRReviewError):
            raise TokenBudgetExceededError(budget=1000, used=2000)

    def test_has_docstring(self):
        assert TokenBudgetExceededError.__doc__ is not None
