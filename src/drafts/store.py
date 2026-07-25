"""작성 중인 내용의 임시 저장.

목적은 하나다. 아이디어를 적다가 화면을 벗어나거나 브라우저를 새로고침해도
쓰던 내용이 사라지지 않게 하는 것.

세션 메모리만 쓰면 새로고침에서 날아가므로 `data/drafts.json`에도 남긴다.
단일 사용자용 로컬 프로그램이므로 파일 한 개로 충분하다.
저장에 실패해도 예외를 밖으로 던지지 않는다. 임시 저장 실패 때문에
사용자가 글을 못 쓰게 되는 것이 더 나쁘기 때문이다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_FILENAME = "drafts.json"


class DraftStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def path(self) -> Path:
        return self.settings.data_dir / _FILENAME

    def _read_all(self) -> dict[str, str]:
        try:
            if not self.path.exists():
                return {}
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            return {str(k): str(v) for k, v in raw.items()}
        except (OSError, ValueError) as exc:
            logger.warning("임시 저장 파일을 읽지 못했습니다: %s", exc)
            return {}

    def _write_all(self, drafts: dict[str, str]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("임시 저장에 실패했습니다: %s", exc)

    def get(self, key: str) -> str:
        return self._read_all().get(key, "")

    def save(self, key: str, text: str) -> None:
        drafts = self._read_all()
        if text and text.strip():
            drafts[key] = text
        else:
            drafts.pop(key, None)
        self._write_all(drafts)

    def clear(self, key: str) -> None:
        drafts = self._read_all()
        if drafts.pop(key, None) is not None:
            self._write_all(drafts)
