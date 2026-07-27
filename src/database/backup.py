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


def backup_to_file(db_path: Path, dest_path: Path) -> bool:
    """`db_path`의 SQLite 온라인 백업을 `dest_path`에 직접 만든다.

    마이그레이션 전 백업처럼 "타임스탬프가 붙은 새 파일"을 만들 때 쓴다.
    `dest_path`는 아직 존재하지 않아야 한다(호출하는 쪽이 항상 새
    파일명을 만들어 넘긴다). DB 파일이 없거나 백업 자체가 실패하면
    예외를 던지지 않고 False를 돌려준다 — 실패 여부와 원인 판단은
    호출한 쪽의 몫이다.
    """
    if not db_path.exists():
        return False
    src = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            src.backup(dest)
        finally:
            dest.close()
    except (OSError, sqlite3.Error) as exc:
        logger.warning("DB 백업(%s → %s)에 실패했습니다: %s", db_path, dest_path, exc)
        return False
    finally:
        src.close()
    return True


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
        tmp_path.unlink()  # backup_to_file은 대상 파일이 없는 상태에서 시작해야 한다

        if not backup_to_file(db_path, tmp_path):
            return None

        return tmp_path.read_bytes()
    except OSError as exc:
        logger.warning("DB 스냅샷 생성에 실패했습니다: %s", exc)
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
