"""Tests for the provider-agnostic LLM layer."""

from unittest.mock import patch

import pytest

from app.services.llm_service import LLMError, generate


class TestProviderSelection:
    """LLM_PROVIDER env var controls which backend handles requests."""

    def test_default_to_openrouter(self):
        """Default provider should be openrouter."""
        from app.core.config import settings

        assert settings.LLM_PROVIDER == "openrouter"

    def test_gemini_provider_delegates(self):
        """When provider is gemini, generate should call gemini_service's generate."""
        with (
            patch("app.services.llm_service.settings.LLM_PROVIDER", "gemini"),
            patch("app.services.gemini_service.generate") as mock_gs,
        ):
            mock_gs.return_value = {"text": "ok", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "latency_ms": 100}
            result = generate(
                prompt="test",
                system_instruction="be helpful",
            )
            assert result["text"] == "ok"
            mock_gs.assert_called_once()

    def test_openrouter_missing_key(self):
        """OpenRouter without API key should raise LLMError."""
        with (
            patch("app.services.llm_service.settings.LLM_PROVIDER", "openrouter"),
            patch("app.services.llm_service.settings.OPENROUTER_API_KEY", ""),
        ):
            with pytest.raises(LLMError, match="OPENROUTER_API_KEY is not configured"):
                generate(prompt="test", system_instruction="helpful")

    def test_openai_missing_key(self):
        """OpenAI without API key should raise LLMError."""
        with (
            patch("app.services.llm_service.settings.LLM_PROVIDER", "openai"),
            patch("app.services.llm_service.settings.OPENAI_API_KEY", ""),
        ):
            with pytest.raises(LLMError, match="OPENAI_API_KEY is not configured"):
                generate(prompt="test", system_instruction="helpful")

    def test_openrouter_uses_correct_base_url(self):
        """OpenRouter should hit the OpenRouter API endpoint."""
        with (
            patch("app.services.llm_service.settings.LLM_PROVIDER", "openrouter"),
            patch("app.services.llm_service.settings.OPENROUTER_API_KEY", "sk-test"),
            patch("app.services.llm_service._openai_chat") as mock_chat,
            patch("app.services.llm_service.settings.LLM_MODEL", "test-model"),
        ):
            mock_chat.return_value.status_code = 200
            mock_chat.return_value.json.return_value = {
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }

            result = generate(prompt="hi", system_instruction="be nice")
            assert result["text"] == "hello"
            assert result["prompt_tokens"] == 5

            # Verify the correct base URL was used
            call_kwargs = mock_chat.call_args.kwargs
            assert "openrouter.ai" in str(call_kwargs)

    def test_openai_uses_correct_base_url(self):
        """OpenAI should hit the OpenAI API endpoint."""
        with (
            patch("app.services.llm_service.settings.LLM_PROVIDER", "openai"),
            patch("app.services.llm_service.settings.OPENAI_API_KEY", "sk-test"),
            patch("app.services.llm_service._openai_chat") as mock_chat,
            patch("app.services.llm_service.settings.OPENAI_MODEL", "gpt-4o-mini"),
        ):
            mock_chat.return_value.status_code = 200
            mock_chat.return_value.json.return_value = {
                "choices": [{"message": {"content": "world"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }

            result = generate(prompt="hi", system_instruction="be nice")
            assert result["text"] == "world"
