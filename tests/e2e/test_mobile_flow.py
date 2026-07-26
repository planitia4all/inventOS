"""모바일(390px) 뷰포트에서 가로 스크롤이 생기지 않는지 확인.

390px는 iPhone 12/13/14 표준 너비다 — 콘텐츠가 이 폭을 넘치면 모바일에서
가로 스크롤이 생겨 사용성이 나빠진다.
"""
from __future__ import annotations


def test_home_has_no_horizontal_scroll_on_mobile(mobile_page):
    scroll_width = mobile_page.evaluate("document.documentElement.scrollWidth")
    client_width = mobile_page.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width + 1  # 1px 여유는 서브픽셀 렌더링 오차 허용


def test_capture_page_has_no_horizontal_scroll_on_mobile(mobile_page):
    mobile_page.get_by_role("button", name="➕ 새 기록").click()
    mobile_page.wait_for_selector("text=아이디어 내용")

    scroll_width = mobile_page.evaluate("document.documentElement.scrollWidth")
    client_width = mobile_page.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width + 1


def test_detail_page_has_no_horizontal_scroll_on_mobile(mobile_page):
    mobile_page.get_by_role("button", name="➕ 새 기록").click()
    mobile_page.wait_for_selector("text=아이디어 내용")
    mobile_page.locator("textarea").first.fill("모바일 가로 스크롤 테스트용 아이디어")
    mobile_page.get_by_role("button", name="저장", exact=True).click()
    mobile_page.wait_for_selector("text=관련 아이디어", timeout=15000)

    scroll_width = mobile_page.evaluate("document.documentElement.scrollWidth")
    client_width = mobile_page.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width + 1
