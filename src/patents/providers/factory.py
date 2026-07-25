"""설정값에 따라 사용 가능한 PatentProvider 목록/인스턴스를 만든다."""
from __future__ import annotations

from src.config.settings import Settings
from src.patents.providers.base import PatentProvider
from src.patents.providers.epo_ops_provider import EpoOpsProvider
from src.patents.providers.kipris_provider import KiprisProvider
from src.patents.providers.manual_provider import ManualPatentProvider
from src.patents.providers.mock_provider import MockPatentProvider
from src.patents.providers.uspto_provider import UsptoProvider

PROVIDER_LABELS = {
    "kipris": "KIPRIS Plus (한국)",
    "epo_ops": "EPO OPS (유럽/해외)",
    "uspto": "USPTO (미국)",
    "mock": "Mock (데모/테스트)",
    "manual": "수동 등록",
}


def available_search_providers(settings: Settings) -> list[str]:
    """자동 검색(search)이 가능한 provider key 목록. 항상 mock은 포함한다."""
    providers = ["mock"]
    if settings.kipris_api_key:
        providers.append("kipris")
    if settings.epo_ops_client_key and settings.epo_ops_client_secret:
        providers.append("epo_ops")
    if settings.uspto_api_key:
        providers.append("uspto")
    return providers


def get_provider(key: str, settings: Settings) -> PatentProvider:
    if key == "mock":
        return MockPatentProvider()
    if key == "manual":
        return ManualPatentProvider()
    if key == "kipris":
        return KiprisProvider(settings.kipris_api_key)
    if key == "epo_ops":
        return EpoOpsProvider(settings.epo_ops_client_key, settings.epo_ops_client_secret)
    if key == "uspto":
        return UsptoProvider(settings.uspto_api_key)
    raise ValueError(f"알 수 없는 Provider 입니다: {key}")
