"""경량 스키마 마이그레이션.

SQLAlchemy의 `create_all`은 없는 테이블만 만들고 기존 테이블에 추가된
컬럼은 반영하지 않는다. 기존 사용자의 발명 데이터를 지우지 않고 컬럼만
덧붙이기 위해, SQLite의 `ALTER TABLE ... ADD COLUMN`으로 누락된 컬럼을
채워 넣는다.

원칙:
- 컬럼 추가만 수행한다. 삭제·타입 변경은 하지 않는다(데이터 손실 방지).
- 이미 존재하는 컬럼은 건너뛴다. 여러 번 실행해도 안전하다.
"""
from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

# 테이블별로 나중에 추가된 컬럼과 SQLite 타입 정의
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "inventions": {
        "refined_content": "TEXT",
        "key_components": "TEXT",
        "operating_principle": "TEXT",
        "differentiation": "TEXT",
        "implementation_method": "TEXT",
        "experiment_notes": "TEXT",
        "review_notes": "TEXT",
        "is_favorite": "BOOLEAN DEFAULT 0",
    },
}


def run_migrations(engine: Engine) -> list[str]:
    """누락된 컬럼을 추가하고, 실제로 추가한 컬럼 목록을 반환한다."""
    inspector = inspect(engine)
    applied: list[str] = []

    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                # create_all이 최신 스키마로 새로 만들었으므로 손댈 것이 없다.
                continue

            present = {col["name"] for col in inspector.get_columns(table)}
            for column_name, column_type in columns.items():
                if column_name in present:
                    continue
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
                )
                applied.append(f"{table}.{column_name}")
                logger.info("마이그레이션: %s.%s 컬럼을 추가했습니다.", table, column_name)

    return applied
