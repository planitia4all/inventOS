"""발명 노트를 Markdown 보고서로 변환한다."""
from __future__ import annotations

import re

from src.database.models import Invention, InventionPatentLink

# Windows에서 금지된 문자(< > : " / \ | ? *) + 제어문자.
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "untitled") -> str:
    """내보내기 파일명에서 Windows 금지 문자를 제거한다.

    현재 발명번호(INV-2026-00001 형식, 항상 서버가 만들고 사용자가 직접
    입력할 수 없음) 기반 파일명은 이 문자들을 포함할 수 없어 실질적으로는
    항상 안전하지만, 나중에 제목 등 사용자 입력 기반 파일명을 쓰게 되더라도
    안전하도록 내보내기 경로에 방어적으로 적용해 둔다.
    """
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or fallback

# (제목, 필드명) 순서대로 출력한다. 비어 있으면 표시만 하고 넘어간다.
_SECTIONS: list[tuple[str, str]] = [
    ("원본 아이디어", "original_idea"),
    ("정리된 발명 내용", "refined_content"),
    ("해결하려는 문제", "problem_to_solve"),
    ("기존 방식 또는 기존 기술", "conventional_method"),
    ("기존 방식의 한계", "conventional_problems"),
    ("핵심 아이디어", "core_principle"),
    ("주요 구성 요소", "key_components"),
    ("작동 원리", "operating_principle"),
    ("기존 기술과 다른 점", "differentiation"),
    ("예상 효과", "expected_effects"),
    ("적용 가능 분야", "applicable_industries"),
    ("구현 방법", "implementation_method"),
    ("실험 기록", "experiment_notes"),
    ("예상되는 어려움", "technical_barriers"),
    ("추가 검토 사항", "review_notes"),
]

_DISCLAIMER = (
    "본 보고서의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 참고자료입니다. "
    "신규성, 진보성, 권리범위 및 특허침해 여부에 대한 법적 판단을 제공하지 않습니다. "
    "특허 출원 또는 사업화 전에는 변리사 등 전문가의 검토가 필요합니다."
)


def _section(index: int, title: str, body: str | None) -> str:
    body = (body or "").strip()
    return f"## {index}. {title}\n\n{body if body else '_(작성되지 않음)_'}\n"


def _patent_block(index: int, link: InventionPatentLink) -> str:
    patent = link.patent
    lines = [f"### 비슷한 기술 {index}", ""]
    lines.append(f"- 발명의 명칭: {patent.title}")
    lines.append(f"- 공개번호: {patent.publication_number}")
    lines.append(f"- 출원인: {patent.applicant or '(미상)'}")
    lines.append(
        f"- 우선일: {patent.priority_date.isoformat() if patent.priority_date else '(미상)'}"
    )
    lines.append(f"- 원문 링크: {patent.source_url or '(없음)'}")
    lines.append(f"- 초록: {patent.abstract_original or '(없음)'}")
    if patent.abstract_translated_ko:
        lines.append(f"- AI 번역: {patent.abstract_translated_ko}")
    if patent.abstract_ai_summary:
        lines.append(f"- AI 요약: {patent.abstract_ai_summary}")
    lines.append(f"- 내 아이디어와 같은 점: {link.similarities or '(작성되지 않음)'}")
    lines.append(f"- 내 아이디어와 다른 점: {link.differences or '(작성되지 않음)'}")
    lines.append(f"- 차별화 아이디어: {link.differentiation_ideas or '(작성되지 않음)'}")
    lines.append("")
    return "\n".join(lines)


def export_invention_markdown(
    invention: Invention,
    patent_links: list[InventionPatentLink] | None = None,
    conclusion: str = "",
) -> str:
    patent_links = patent_links or []

    parts = [f"# {invention.title}", ""]
    parts.append(f"- 발명번호: {invention.invention_no}")
    parts.append(f"- 상태: {invention.status}")
    parts.append(f"- 기술분야: {invention.technical_field or '(미상)'}")
    parts.append("")

    index = 1
    for title, field_name in _SECTIONS:
        parts.append(_section(index, title, getattr(invention, field_name, None)))
        index += 1

    tag_names = [link.tag.name for link in invention.tag_links]
    parts.append(_section(index, "검색 키워드", ", ".join(tag_names)))
    index += 1

    parts.append(f"## {index}. 비슷한 기술(선행특허) 목록\n")
    if patent_links:
        for i, link in enumerate(patent_links, start=1):
            parts.append(_patent_block(i, link))
    else:
        parts.append("_(연결된 선행특허 없음)_\n")
    index += 1

    parts.append(_section(index, "현재 결론", conclusion))

    parts.append(f"---\n\n{_DISCLAIMER}\n")

    return "\n".join(parts)
