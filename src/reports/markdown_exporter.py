"""발명 노트를 Markdown 보고서로 변환한다.

요구사항 11절의 출력 구조를 따른다.
"""
from __future__ import annotations

from src.database.models import Invention, InventionPatentLink


def _section(title: str, body: str | None) -> str:
    body = (body or "").strip()
    return f"## {title}\n\n{body if body else '_(작성되지 않음)_'}\n"


def _patent_block(index: int, link: InventionPatentLink) -> str:
    patent = link.patent
    lines = [f"### 선행특허 {index}", ""]
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
    additional_research: str = "",
) -> str:
    patent_links = patent_links or []

    parts = [f"# {invention.title}", ""]
    parts.append(f"- 발명번호: {invention.invention_no}")
    parts.append(f"- 상태: {invention.status}")
    parts.append(f"- 기술분야: {invention.technical_field or '(미상)'}")
    parts.append("")

    parts.append(_section("1. 최초 아이디어", invention.original_idea))
    parts.append(_section("2. 해결하려는 문제", invention.problem_to_solve))
    parts.append(_section("3. 기존 방식", invention.conventional_method))
    parts.append(_section("4. 기존 방식의 문제점", invention.conventional_problems))
    parts.append(_section("5. 핵심 해결 원리", invention.core_principle))
    parts.append(_section("6. 예상 효과", invention.expected_effects))
    parts.append(_section("7. 예상 기술 장벽", invention.technical_barriers))
    parts.append(_section("8. 검색 키워드", ", ".join(invention.keywords or [])))

    parts.append("## 9. 선행특허 목록\n")
    if patent_links:
        for i, link in enumerate(patent_links, start=1):
            parts.append(_patent_block(i, link))
    else:
        parts.append("_(연결된 선행특허 없음)_\n")

    parts.append(_section("10. 현재 결론", conclusion))
    parts.append(_section("11. 추가 조사사항", additional_research))

    parts.append(
        "---\n\n"
        "본 보고서의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 참고자료입니다. "
        "신규성, 진보성, 권리범위 및 특허침해 여부에 대한 법적 판단을 제공하지 않습니다. "
        "특허 출원 또는 사업화 전에는 변리사 등 전문가의 검토가 필요합니다.\n"
    )

    return "\n".join(parts)
