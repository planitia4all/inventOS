"""실행 중인 SQLite DB의 일관된 백업 스냅샷을 만든다.

`db_path.read_bytes()`로 파일을 직접 읽으면, 앱이 쓰기 작업 중이거나
저널/WAL 파일에 아직 커밋되지 않은 변경이 있을 때 일관되지 않은 백업이
만들어질 수 있다. SQLite의 온라인 백업 API(`sqlite3.Connection.backup`)는
페이지 단위로 안전하게 복사해 항상 일관된 스냅샷을 보장한다.
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def create_consistent_snapshot(db_path: Path) -> bytes | None:
    """`db_path`의 SQLite 온라인 백업을 만들어 바이트로 돌려준다.

    DB 파일이 없으면 None. 백업 자체가 실패해도 예외를 밖으로 던지지
    않고 None을 돌려준다 — 호출한 쪽(설정 화면)이 사용자에게 안내한다.
    """
    if not db_path.exists():
        return None

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        src = sqlite3.connect(str(db_path))
        try:
            dest = sqlite3.connect(str(tmp_path))
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()

        return tmp_path.read_bytes()
    except (OSError, sqlite3.Error) as exc:
        logger.warning("DB 스냅샷 생성에 실패했습니다: %s", exc)
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
