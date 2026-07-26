"""SQLite FTS5 기반 통합 검색.

제목만이 아니라 원본 메모, 발명 내용(정리된 내용/핵심 원리/실험 기록 등),
태그, 첨부파일 이름까지 한 번에 검색한다.

색인은 완벽한 실시간 트리거 대신, 의미 있는 변경이 있을 때마다
`reindex_invention()`을 명시적으로 호출하는 방식으로 유지한다 — 발명
내용이 여러 테이블(태그, 첨부파일 등)에 걸쳐 있어서 SQL 트리거만으로는
깔끔하게 표현하기 어렵고, 로컬 단일 사용자 프로그램 규모에서는 이 편이
더 단순하고 디버깅하기 쉽다.
"""
from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

FTS_TABLE = "invention_search_index"

# Invention의 텍스트 본문 필드 (제목/원본과는 별도로 색인한다)
_CONTENT_FIELDS = (
    "technical_field",
    "refined_content",
    "problem_to_solve",
    "conventional_method",
    "conventional_problems",
    "core_principle",
    "key_components",
    "operating_principle",
    "differentiation",
    "expected_effects",
    "technical_barriers",
    "applicable_industries",
    "implementation_method",
    "experiment_notes",
    "review_notes",
)


def ensure_index_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
                    invention_id UNINDEXED,
                    title,
                    original_idea,
                    content_text,
                    tags,
                    attachment_names
                )
                """
            )
        )


def _sanitize_tokens(query: str) -> list[str]:
    """FTS5 MATCH 구문에 안전하게 넣을 수 있도록 토큰을 정리한다."""
    tokens = []
    for raw in query.split():
        cleaned = "".join(ch for ch in raw if ch.isalnum())
        if cleaned:
            tokens.append(cleaned)
    return tokens


class SearchIndexService:
    def __init__(self, session: Session):
        self.session = session

    def reindex_invention(self, invention_id: str) -> None:
        """이 발명의 색인을 최신 내용으로 다시 만든다.

        `invention.attachments` / `invention.tag_links` 관계를 그대로 쓰지
        않고 매번 직접 조회한다 — 같은 세션 안에서 이 관계가 한 번이라도
        지연 로딩되어 캐시된 뒤에는, FK만 직접 설정하고 flush한 자식
        레코드(예: 새 첨부파일)가 추가돼도 이미 로딩된 컬렉션이 자동으로
        갱신되지 않기 때문이다 (SQLAlchemy의 일반적인 동작). 직접 쿼리하면
        항상 flush된 최신 상태를 본다.
        """
        from src.database.models import Attachment, Invention, InventionTag, Tag

        invention = self.session.get(Invention, invention_id)
        if invention is None:
            self.remove(invention_id)
            return

        content_text = " ".join(
            filter(None, (getattr(invention, f) for f in _CONTENT_FIELDS))
        )
        tag_names = " ".join(
            name
            for (name,) in self.session.query(Tag.name)
            .join(InventionTag, InventionTag.tag_id == Tag.id)
            .filter(InventionTag.invention_id == invention_id)
            .all()
        )
        attachment_names = " ".join(
            name
            for (name,) in self.session.query(Attachment.original_filename)
            .filter(Attachment.invention_id == invention_id)
            .all()
        )

        self.remove(invention_id)
        self.session.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE}
                    (invention_id, title, original_idea, content_text, tags, attachment_names)
                VALUES (:invention_id, :title, :original_idea, :content_text, :tags, :attachment_names)
                """
            ),
            {
                "invention_id": invention.id,
                "title": invention.title,
                "original_idea": invention.original_idea,
                "content_text": content_text,
                "tags": tag_names,
                "attachment_names": attachment_names,
            },
        )

    def remove(self, invention_id: str) -> None:
        self.session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE invention_id = :invention_id"),
            {"invention_id": invention_id},
        )

    def rebuild_all(self) -> int:
        """모든 발명의 색인을 처음부터 다시 만든다. 마이그레이션/복구용."""
        from src.database.models import Invention

        self.session.execute(text(f"DELETE FROM {FTS_TABLE}"))
        count = 0
        for invention in self.session.query(Invention):
            self.reindex_invention(invention.id)
            count += 1
        return count

    def search(self, query: str, limit: int = 50) -> list[str]:
        """검색어와 일치하는 발명 id를 관련도 순으로 반환한다."""
        tokens = _sanitize_tokens(query)
        if not tokens:
            return []

        match_expr = " ".join(f'{token}*' for token in tokens)
        rows = self.session.execute(
            text(
                f"""
                SELECT invention_id FROM {FTS_TABLE}
                WHERE {FTS_TABLE} MATCH :match_expr
                ORDER BY rank
                LIMIT :limit
                """
            ),
            {"match_expr": match_expr, "limit": limit},
        )
        return [row[0] for row in rows]
