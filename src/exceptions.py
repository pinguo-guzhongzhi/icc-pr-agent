"""Custom exceptions for the PR Review system."""


class PRReviewError(Exception):
    """Base exception for all PR Review errors."""


class UnknownPlatformError(PRReviewError):
    """PR link cannot be recognized as a supported platform."""


class CredentialMissingError(PRReviewError):
    """Platform credentials are not configured."""


class PlatformAPIError(PRReviewError):
    """Platform API call failed."""


class TemplateNotFoundError(PRReviewError):
    """Specified template file does not exist."""


class AIModelError(PRReviewError):
    """AI model invocation failed."""


class CommentWriteBackError(PRReviewError):
    """Failed to write back review comment to platform."""


class EmptyDiffError(PRReviewError):
    """PR diff is empty — no code changes to review."""


class AllFilesExcludedError(PRReviewError):
    """All files in the diff were excluded by filter rules."""


class ExcludeConfigError(PRReviewError):
    """Exclude configuration file has an invalid format."""


class SymbolIndexError(PRReviewError):
    """符号索引构建或查询失败。"""


class SubAgentTimeoutError(PRReviewError):
    """子 Agent 审查超时。"""


class TokenBudgetExceededError(PRReviewError):
    """单次 PR 审查的 token 消耗超出预算，触发熔断。"""

    def __init__(self, budget: int, used: int, message: str = "") -> None:
        self.budget = budget
        self.used = used
        super().__init__(
            message or f"Token 预算已耗尽: 已用 {used}, 预算 {budget}"
        )
