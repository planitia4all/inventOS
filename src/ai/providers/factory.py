"""설정값에 따라 AIProvider 인스턴스를 만든다.

API 키가 없거나 provider 초기화에 실패해도 MockAIProvider로
자동 대체되어 프로그램이 계속 동작해야 한다. 다만 "왜" 대체됐는지는
항상 명확한 경고 메시지로 알려준다 — 조용히 Mock으로 넘어가지 않는다.

모델 ID가 잘못된 경우(존재하지 않는 모델 등)는 여기서 검증하지 않는다 —
실제 API 호출 시점에 Anthropic API가 오류를 반환하고, 그 오류는
`AIProviderError`로 감싸져 호출한 화면(발명 상세의 'AI로 검토하기')에
그대로 표시된다. 즉 "모델 ID가 잘못됨"은 Mock으로 조용히 전환되는 게
아니라 실행할 때마다 명확한 오류로 보인다.
"""
from __future__ import annotations

from src.ai.base import AIProvider, AIProviderError
from src.ai.mock_provider import MockAIProvider
from src.config.settings import PLANNED_AI_PROVIDERS, SUPPORTED_AI_PROVIDERS, Settings


def get_ai_provider(settings: Settings) -> tuple[AIProvider, str | None]:
    """Provider 인스턴스와, 발생 시 Mock으로 대체된 이유(경고 메시지)를 반환한다."""
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        if not (settings.anthropic_model or "").strip():
            return (
                MockAIProvider(),
                "Anthropic 모델 ID가 비어 있습니다. .env의 ANTHROPIC_MODEL을 "
                "설정하세요 (예: claude-sonnet-5). Mock으로 동작합니다.",
            )
        try:
            from src.ai.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider(
                settings.anthropic_api_key, model=settings.anthropic_model
            ), None
        except AIProviderError as exc:
            return MockAIProvider(), str(exc)

    if settings.ai_provider in PLANNED_AI_PROVIDERS:
        return (
            MockAIProvider(),
            f"'{settings.ai_provider}' Provider는 아직 지원하지 않습니다 (향후 지원 예정). "
            "현재는 mock 또는 anthropic만 사용할 수 있습니다. Mock으로 동작합니다.",
        )

    if settings.ai_provider not in ("mock", "", *SUPPORTED_AI_PROVIDERS):
        return MockAIProvider(), f"지원하지 않는 AI Provider입니다: {settings.ai_provider}"

    if settings.ai_provider == "anthropic" and not settings.anthropic_api_key:
        return MockAIProvider(), "Anthropic API 키가 없어 Mock AI로 동작합니다."

    return MockAIProvider(), None
