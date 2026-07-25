"""설정값에 따라 AIProvider 인스턴스를 만든다.

API 키가 없거나 provider 초기화에 실패해도 MockAIProvider로
자동 대체되어 프로그램이 계속 동작해야 한다.
"""
from __future__ import annotations

from src.ai.base import AIProvider, AIProviderError
from src.ai.mock_provider import MockAIProvider
from src.config.settings import Settings


def get_ai_provider(settings: Settings) -> tuple[AIProvider, str | None]:
    """Provider 인스턴스와, 발생 시 Mock으로 대체된 이유(경고 메시지)를 반환한다."""
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        try:
            from src.ai.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider(
                settings.anthropic_api_key, model=settings.anthropic_model
            ), None
        except AIProviderError as exc:
            return MockAIProvider(), str(exc)

    if settings.ai_provider not in ("mock", "", "anthropic"):
        return MockAIProvider(), f"지원하지 않는 AI Provider입니다: {settings.ai_provider}"

    if settings.ai_provider == "anthropic" and not settings.anthropic_api_key:
        return MockAIProvider(), "Anthropic API 키가 없어 Mock AI로 동작합니다."

    return MockAIProvider(), None
