"""InventOS 설정 로딩.

API 키와 사용자 설정은 .env 파일 또는 OS 환경변수에서만 읽는다.
데이터베이스에 평문으로 저장하지 않는다.

환경변수가 잘못 입력되어도(숫자 자리에 문자열 등) 앱 시작 자체가
traceback과 함께 죽으면 안 된다 — 안전한 기본값으로 대체하고 로그만 남긴다.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(_PROJECT_ROOT / ".env")

# 설정 화면 "앱 정보"에 표시하는 버전. 사용자에게 보여주는 용도일 뿐 자동
# 업데이트 체크 등에는 쓰지 않는다.
APP_VERSION = "0.4.0"

# 현재 코드가 실제로 만들 수 있는 AI Provider. "openai"는 .env/설정 화면에
# 자리는 마련해 두었지만 아직 구현하지 않았다 — src/ai/providers/factory.py가
# 이 목록 밖의 값이면 이유를 밝히고 Mock으로 대체한다.
SUPPORTED_AI_PROVIDERS = ("mock", "anthropic")
PLANNED_AI_PROVIDERS = ("openai",)  # 설정은 받아두지만 아직 미구현


def _mask(value: str | None) -> str:
    """UI/로그 표시용으로 키를 마스킹한다."""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _safe_int(env_var: str, default: int) -> int:
    raw = os.getenv(env_var)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "환경변수 %s 값 '%s'을(를) 숫자로 읽을 수 없어 기본값 %d을 사용합니다.",
            env_var,
            raw,
            default,
        )
        return default


@dataclass
class Settings:
    user_name: str = field(default_factory=lambda: os.getenv("INVENTOS_USER_NAME", ""))
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("INVENTOS_DATA_DIR") or str(_PROJECT_ROOT / "data")
        )
    )
    language: str = field(default_factory=lambda: os.getenv("INVENTOS_LANGUAGE", "ko"))
    default_search_limit: int = field(
        default_factory=lambda: _safe_int("INVENTOS_DEFAULT_SEARCH_LIMIT", 20)
    )

    kipris_api_key: str = field(default_factory=lambda: os.getenv("KIPRIS_API_KEY", ""))
    epo_ops_client_key: str = field(default_factory=lambda: os.getenv("EPO_OPS_CLIENT_KEY", ""))
    epo_ops_client_secret: str = field(
        default_factory=lambda: os.getenv("EPO_OPS_CLIENT_SECRET", "")
    )
    uspto_api_key: str = field(default_factory=lambda: os.getenv("USPTO_API_KEY", ""))

    ai_provider: str = field(default_factory=lambda: os.getenv("INVENTOS_AI_PROVIDER", "mock"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    )
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "inventos.db"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    def masked(self) -> dict[str, str]:
        """설정 화면/로그에 안전하게 노출할 수 있는 마스킹된 값."""
        return {
            "kipris_api_key": _mask(self.kipris_api_key),
            "epo_ops_client_key": _mask(self.epo_ops_client_key),
            "epo_ops_client_secret": _mask(self.epo_ops_client_secret),
            "uspto_api_key": _mask(self.uspto_api_key),
            "anthropic_api_key": _mask(self.anthropic_api_key),
            "openai_api_key": _mask(self.openai_api_key),
        }


def get_settings() -> Settings:
    return Settings()
