"""Tests for error hierarchy and redaction."""

from __future__ import annotations

from metarelay.core.errors import (
    ConfigError,
    ConnectionError,
    DispatchError,
    EventStoreError,
    MetarelayError,
    redact_error,
)


class TestErrorHierarchy:
    """Tests for error class hierarchy."""

    def test_config_error_is_metarelay_error(self) -> None:
        assert issubclass(ConfigError, MetarelayError)

    def test_connection_error_is_metarelay_error(self) -> None:
        assert issubclass(ConnectionError, MetarelayError)

    def test_dispatch_error_is_metarelay_error(self) -> None:
        assert issubclass(DispatchError, MetarelayError)

    def test_event_store_error_is_metarelay_error(self) -> None:
        assert issubclass(EventStoreError, MetarelayError)


class TestRedactError:
    """Tests for sensitive data redaction."""

    def test_redacts_github_token_ghp(self) -> None:
        error = Exception("Failed with token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
        result = redact_error(error)
        assert "ghp_" not in str(result)
        assert "<REDACTED_TOKEN>" in str(result)

    def test_redacts_github_token_gho(self) -> None:
        error = Exception("Token gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
        result = redact_error(error)
        assert "gho_" not in str(result)
        assert "<REDACTED_TOKEN>" in str(result)

    def test_redacts_github_pat(self) -> None:
        error = Exception("Using github_pat_ABCDEFGHIJKLMNOPQRSTUV")
        result = redact_error(error)
        assert "github_pat_" not in str(result)
        assert "<REDACTED_TOKEN>" in str(result)

    def test_redacts_jwt(self) -> None:
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        error = Exception(f"Key: {jwt}")
        result = redact_error(error)
        assert "eyJ" not in str(result)
        assert "<REDACTED_JWT>" in str(result)

    def test_redacts_url_credentials(self) -> None:
        error = Exception("Connect to https://user:password123@host.com/path")
        result = redact_error(error)
        assert "password123" not in str(result)
        assert "<REDACTED_CREDS>" in str(result)

    def test_redacts_authorization_header(self) -> None:
        error = Exception("Authorization: Bearer my-secret-token-value")
        result = redact_error(error)
        assert "my-secret-token-value" not in str(result)
        assert "<REDACTED_TOKEN>" in str(result)

    def test_preserves_original_exception(self) -> None:
        original = ValueError("original error ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
        result = redact_error(original)
        assert result.__cause__ is original

    def test_result_is_metarelay_error(self) -> None:
        result = redact_error(Exception("test"))
        assert isinstance(result, MetarelayError)

    def test_no_redaction_needed(self) -> None:
        error = Exception("Normal error message")
        result = redact_error(error)
        assert str(result) == "Normal error message"
