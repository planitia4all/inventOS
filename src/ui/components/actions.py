"""쓰기 동작 + 새로고침을 안전하게 묶는 헬퍼.

주의: `with get_session() as session: ... st.rerun()`처럼 DB 세션을 연 채로
`st.rerun()`을 호출하면 안 된다. `get_session()`은 `with` 블록을 정상적으로
빠져나갈 때 커밋하는데, `st.rerun()`은 실행을 즉시 끊어버려서 블록이
정상 종료되지 못하고 세션이 커밋 없이 닫힌다 — 즉 방금 저장한 내용이
그대로 사라진다. 이 함수는 쓰기를 완전히 끝내고 커밋까지 마친 다음에만
새로고침하도록 강제한다.
"""
from __future__ import annotations

from typing import Callable

import streamlit as st

from src.database.engine import get_session


def run_and_rerun(action: Callable[[object], None]) -> None:
    """`action(session)`을 짧은 세션 안에서 실행해 커밋까지 완료한 뒤 새로고침한다."""
    with get_session() as session:
        action(session)
    st.rerun()
