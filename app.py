"""InventOS - 발명 노트.

실행: streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src.database.engine import DataDirectoryError, init_engine
from src.database.migrations import MigrationBackupError
from src.ui.components.layout import apply_base_style, go, legal_notice, nav_row
from src.ui.pages import home, invention_detail, invention_list, quick_capture, settings

st.set_page_config(
    page_title="발명 노트",
    page_icon="💡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

apply_base_style()
try:
    init_engine()
except (MigrationBackupError, DataDirectoryError) as exc:
    st.error(str(exc))
    st.stop()

if "page" not in st.session_state:
    st.session_state.page = "home"
if "current_invention_id" not in st.session_state:
    st.session_state.current_invention_id = None

page = st.session_state.page

# 화면을 옮기기 전에 쓰다 만 내용을 먼저 지켜낸다.
quick_capture.persist_pending_draft()

# 상단 이동 버튼 — 사이드바에 의존하지 않아 모바일에서도 바로 보인다.
nav = nav_row(3)
if nav[0].button("🏠 홈", key="nav_home"):
    go("home")
if nav[1].button("➕ 새 기록", key="nav_capture"):
    quick_capture.clear_derive_context()
    go("capture")
if nav[2].button("📚 목록", key="nav_list"):
    go("list")

if page == "home":
    home.render()
elif page == "capture":
    quick_capture.render()
elif page == "detail":
    invention_detail.render(st.session_state.current_invention_id)
elif page == "list":
    invention_list.render()
elif page == "settings":
    settings.render()
else:
    home.render()

st.divider()
footer = nav_row(2)
if footer[0].button("⚙️ 설정", key="nav_settings"):
    go("settings")
with footer[1]:
    legal_notice()
