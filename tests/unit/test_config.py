"""Unit tests for src/config.py."""

from src.config import Config

# All tests use a non-existent dotenv path to avoid loading the real .env file.
_NO_DOTENV = "/tmp/__nonexistent__.env"


class TestConfigFromEnv:
    def test_defaults(self):
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.github_token == ""
        assert cfg.gitlab_url == "https://gitlab.com"
        assert cfg.llm_model == "gpt-4"
        assert cfg.log_level == "INFO"
        assert cfg.review_storage_dir == ".pr_reviews"
        assert cfg.pr_review_exclude == []
        assert cfg.skills_dir == ""

    def test_skills_dir(self, monkeypatch):
        monkeypatch.setenv("SKILLS_DIR", "/custom/skills")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.skills_dir == "/custom/skills"

    def test_loads_tokens(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "gh_tok")
        monkeypatch.setenv("GITLAB_TOKEN", "gl_tok")
        monkeypatch.setenv("CODEUP_TOKEN", "cu_tok")
        monkeypatch.setenv("LLM_API_KEY", "sk-key")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.github_token == "gh_tok"
        assert cfg.gitlab_token == "gl_tok"
        assert cfg.codeup_token == "cu_tok"
        assert cfg.llm_api_key == "sk-key"

    def test_loads_custom_values(self, monkeypatch):
        monkeypatch.setenv("GITLAB_URL", "https://git.example.com")
        monkeypatch.setenv("LLM_MODEL", "gpt-3.5-turbo")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("REVIEW_STORAGE_DIR", "/tmp/reviews")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.gitlab_url == "https://git.example.com"
        assert cfg.llm_model == "gpt-3.5-turbo"
        assert cfg.llm_base_url == "https://api.example.com"
        assert cfg.log_level == "DEBUG"
        assert cfg.review_storage_dir == "/tmp/reviews"

    def test_parses_exclude_patterns(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_EXCLUDE", "*.lock,*.png, docs/**")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.pr_review_exclude == ["*.lock", "*.png", "docs/**"]

    def test_empty_exclude_patterns(self):
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.pr_review_exclude == []

    def test_webhook_secrets(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", "wh_gh")
        monkeypatch.setenv("WEBHOOK_SECRET_GITLAB", "wh_gl")
        monkeypatch.setenv("WEBHOOK_SECRET_CODEUP", "wh_cu")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.webhook_secret_github == "wh_gh"
        assert cfg.webhook_secret_gitlab == "wh_gl"
        assert cfg.webhook_secret_codeup == "wh_cu"

    def test_codeup_org_id(self, monkeypatch):
        monkeypatch.setenv("CODEUP_ORG_ID", "org123")
        cfg = Config.from_env(dotenv_path=_NO_DOTENV)
        assert cfg.codeup_org_id == "org123"

    def test_loads_from_dotenv_file(self, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text("GITHUB_TOKEN=from_file\nLLM_MODEL=claude\n")
        cfg = Config.from_env(dotenv_path=str(dotenv))
        assert cfg.github_token == "from_file"
        assert cfg.llm_model == "claude"
