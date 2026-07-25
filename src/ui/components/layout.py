"""공통 레이아웃 요소와 모바일 대응 스타일.

PC와 모바일에서 같은 화면을 쓰되, 좁은 화면에서는 1열로 접히고
버튼과 입력창이 충분히 커지도록 CSS를 주입한다.
"""
from __future__ import annotations

import streamlit as st

_MOBILE_CSS = """
<style>
/* 본문 폭과 여백 — 모바일에서 화면을 꽉 쓰도록 */
.block-container {
    padding-top: 2.2rem;
    padding-bottom: 5rem;
    max-width: 900px;
}

/* 버튼: 터치 영역 확보 + 가로 꽉 채우기 */
div[data-testid="stButton"] {
    width: 100%;
}
.stButton > button {
    min-height: 2.9rem;
    font-size: 1rem;
    border-radius: 10px;
    width: 100%;
}


/* 입력창: 글 쓰기 편한 크기 */
.stTextArea textarea {
    font-size: 1.02rem;
    line-height: 1.6;
}
.stTextInput input {
    min-height: 2.7rem;
    font-size: 1rem;
}

/* 카드 */
.inv-card {
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 12px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.65rem;
    background: rgba(250, 250, 250, 0.6);
}
.inv-card-title {
    font-weight: 600;
    font-size: 1.05rem;
    margin-bottom: 0.25rem;
    word-break: break-word;
}
.inv-card-meta {
    font-size: 0.82rem;
    opacity: 0.7;
    margin-bottom: 0.4rem;
}
.inv-card-body {
    font-size: 0.94rem;
    opacity: 0.9;
    line-height: 1.5;
    word-break: break-word;
}
.inv-tag {
    display: inline-block;
    font-size: 0.78rem;
    padding: 0.1rem 0.5rem;
    margin: 0.15rem 0.25rem 0 0;
    border-radius: 999px;
    background: rgba(120, 140, 255, 0.16);
}

/* 좁은 화면: 본문 컬럼을 1열로 접고 여백을 줄인다 */
@media (max-width: 720px) {
    .block-container {
        padding-left: 0.85rem;
        padding-right: 0.85rem;
        padding-top: 0.8rem;
    }
    div[data-testid="stHorizontalBlock"]:not(:has(.inv-nav-marker)) {
        flex-direction: column;
        gap: 0.4rem;
    }
    div[data-testid="stHorizontalBlock"]:not(:has(.inv-nav-marker))
        > div[data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    /* 이동 버튼 줄: 모바일에서는 다른 컬럼과 마찬가지로 세로로 쌓인다.
       한 줄로 욱여넣으면 라벨이 좁아져 글자가 잘리므로, 세로로 쌓아
       버튼을 크게 유지하는 쪽을 택한다. */
    .stButton > button {
        min-height: 3.1rem;
    }
}
</style>
"""


def apply_base_style() -> None:
    st.markdown(_MOBILE_CSS, unsafe_allow_html=True)


def nav_row(count: int):
    """이동 버튼용 가로 줄. PC에서는 한 줄, 모바일에서는 세로로 쌓인다."""
    return st.columns(count)


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def idea_card(
    title: str,
    meta: str = "",
    body: str = "",
    tags: list[str] | None = None,
) -> None:
    """목록에서 아이디어 한 건을 카드로 보여준다 (모바일에서 표보다 읽기 쉽다)."""
    parts = ['<div class="inv-card">']
    parts.append(f'<div class="inv-card-title">{_escape(title)}</div>')
    if meta:
        parts.append(f'<div class="inv-card-meta">{_escape(meta)}</div>')
    if body:
        snippet = body.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:120].rstrip() + "..."
        parts.append(f'<div class="inv-card-body">{_escape(snippet)}</div>')
    if tags:
        tag_html = "".join(f'<span class="inv-tag">#{_escape(t)}</span>' for t in tags)
        parts.append(f"<div>{tag_html}</div>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def go(page: str, invention_id: str | None = None) -> None:
    """화면 이동 헬퍼."""
    st.session_state.page = page
    if invention_id is not None or page in ("home", "list", "capture"):
        st.session_state.current_invention_id = invention_id
    st.rerun()


def legal_notice() -> None:
    with st.expander("법적 안내", expanded=False):
        st.caption(
            "본 프로그램의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 "
            "참고자료입니다. 신규성, 진보성, 권리범위 및 특허침해 여부에 대한 "
            "법적 판단을 제공하지 않습니다. 특허 출원 또는 사업화 전에는 "
            "변리사 등 전문가의 검토가 필요합니다."
        )
