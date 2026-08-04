"""Tests for main.py::_user_facing_error, the raw-exception-to-UI-message translator."""

from main import _user_facing_error


class TestUserFacingError:
    def test_missing_api_key_shows_config_message(self):
        exc = Exception(
            "The api_key client option must be set either by passing api_key "
            "to the client or by setting the GROQ_API_KEY environment variable"
        )
        assert "configured correctly" in _user_facing_error(exc)

    def test_rate_limit_shows_rate_limit_message(self):
        exc = Exception("Error code: 429 - rate_limit_exceeded")
        assert "rate-limited" in _user_facing_error(exc)

    def test_tool_use_failure_shows_formatting_message(self):
        exc = Exception("Failed to call a function. Please adjust your prompt.")
        assert "formatting" in _user_facing_error(exc)

    def test_connection_failure_shows_reach_message(self):
        exc = Exception("ConnectError: Temporary failure in name resolution")
        assert "Couldn't reach" in _user_facing_error(exc)

    def test_unrecognized_error_falls_back_to_generic_message(self):
        exc = Exception("something completely unexpected happened")
        assert _user_facing_error(exc) == (
            "Something went wrong while generating this brief. Please try again."
        )
