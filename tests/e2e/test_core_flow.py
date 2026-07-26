"""핵심 사용자 흐름의 실제 브라우저 자동화 검증.

이전 단계(RC 이전)에서는 이런 흐름을 Playwright로 손으로 실행해 눈으로만
확인하고 코드로 남기지 않았다 — 그래서 다음에 똑같이 다시 확인하려면
매번 수동으로 반복해야 했다. 이 파일은 그중 핵심 흐름만이라도 실제
자동화 테스트로 남겨, 회귀를 코드로 잡을 수 있게 한다.

Streamlit 특유의 동작 때문에 다음을 지켜야 안정적으로 통과한다:
- `st.expander(..., expanded=조건)`는 조건이 바뀌면(예: 대기 건수가
  0이 됨) 다음 렌더에서 다시 접힌다 — 반영 후 다시 펼쳐서 확인해야 한다.
- 위젯 라벨은 `get_by_label()`로 찾는 게 `st.form` 안 textarea 순서에
  의존하는 것보다 훨씬 안정적이다.
"""
from __future__ import annotations

import re


def test_quick_idea_save_and_appears_on_home(page):
    """홈에서 '새 아이디어 기록'으로 들어가 메모만 적고 저장하면, 상세
    화면으로 이동하고 홈의 '최근 작성한 아이디어'에도 나타나야 한다."""
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")

    memo = "E2E 테스트: 유리기판에 금속 핀을 먼저 배열하는 방식"
    page.locator("textarea").first.fill(memo)
    page.get_by_role("button", name="저장", exact=True).click()

    # 저장에 성공하면 상세 화면으로 이동한다 — 원본 메모가 그대로 보여야 한다.
    page.wait_for_selector(f"text={memo}", timeout=15000)

    page.get_by_role("button", name="🏠 홈").click()
    page.wait_for_selector("text=최근 작성한 아이디어")
    assert "E2E 테스트" in page.inner_text("body")


def test_unified_search_finds_saved_idea(page):
    """빠른 기록으로 저장한 고유 문구가 목록 화면 검색에서 실제로 나와야 한다."""
    unique_phrase = "E2E검색전용고유문구그래핀히팅"
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")
    page.locator("textarea").first.fill(f"검색 테스트 메모 {unique_phrase}")
    page.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_selector("text=관련 아이디어", timeout=15000)

    page.get_by_role("button", name="📚 목록").click()
    page.wait_for_selector("text=검색")
    page.get_by_placeholder("제목, 내용, 태그, 첨부파일 이름으로 찾기").fill(unique_phrase)
    page.keyboard.press("Enter")

    page.wait_for_selector(f"text={unique_phrase}", timeout=15000)


def test_ai_mock_review_and_full_apply(page):
    """AI로 검토하기(Mock) → 결과 생성 → 전체 반영까지 실제로 동작해야 한다.

    반영에 성공하면 대기 건수가 줄고, 발명 필드에 내용이 복사되며,
    Timeline/버전 기록이 함께 늘어난다.
    """
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")
    page.locator("textarea").first.fill("AI 검토 테스트용 아이디어: 자동 정렬 지그 설계")
    page.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_selector("text=관련 아이디어", timeout=15000)

    page.get_by_text("🤖 AI로 검토하기").click()
    page.get_by_role("button", name="아이디어 정리", exact=True).click()

    page.wait_for_selector("text=대기 1건", timeout=20000)
    page.get_by_role("button", name="전체 반영").click(timeout=15000)

    # 반영되면 대기 건수가 0으로 바뀐다 — 이 시점부터 결과 expander는
    # 다시 접혀 있으므로, 내용을 확인하려면 한 번 더 펼쳐야 한다.
    page.wait_for_selector("text=대기 0건", timeout=15000)
    page.get_by_text(re.compile(r"AI 검토 결과 \(")).click()
    page.wait_for_selector("text=반영된 항목", timeout=10000)

    body = page.inner_text("body")
    assert "Traceback" not in body


def test_ai_mock_review_partial_apply_ui_opens_without_crash(page):
    """'일부만 반영' 확장 패널이 원문 traceback 없이 정상적으로 열려야 한다.

    실제 반영 로직(구조화된 값이 없으면 원문 전체로 대체하지 않는 정책 등)은
    tests/test_ai_results.py에서 이미 충분히 단위 테스트로 검증했다 — 여기서는
    UI 배선이 실제 브라우저에서 깨지지 않는지만 확인한다.
    """
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")
    page.locator("textarea").first.fill("AI 부분 반영 UI 테스트용 아이디어")
    page.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_selector("text=관련 아이디어", timeout=15000)

    page.get_by_text("🤖 AI로 검토하기").click()
    page.get_by_role("button", name="아이디어 정리", exact=True).click()
    page.wait_for_selector("text=대기 1건", timeout=20000)

    page.locator("summary", has_text="일부만 반영").click(timeout=15000)
    page.wait_for_selector("text=반영할 항목 선택", timeout=10000)

    body = page.inner_text("body")
    assert "Traceback" not in body


def test_experiment_addition(page):
    """실험 기록 추가 폼이 실제로 동작해 목록에 반영되어야 한다."""
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")
    page.locator("textarea").first.fill("실험 기록 테스트용 아이디어")
    page.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_selector("text=관련 아이디어", timeout=15000)

    page.get_by_text(re.compile(r"실험 기록 \(")).click()
    page.get_by_label("조건").fill("E2E 실험 조건: 온도 25도")
    page.get_by_label("결과").fill("E2E 실험 결과: 정상 동작 확인")
    page.get_by_role("button", name="실험 기록 추가").click()

    page.wait_for_selector("text=E2E 실험 조건: 온도 25도", timeout=15000)


def test_derived_idea_creation(page):
    """상세 화면에서 파생 아이디어를 만들면 부모-자식 관계가 화면에 보여야 한다."""
    parent_memo = "파생 테스트용 부모 아이디어"
    page.get_by_role("button", name="➕ 새 기록").click()
    page.wait_for_selector("text=아이디어 내용")
    page.locator("textarea").first.fill(parent_memo)
    page.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_selector("text=관련 아이디어", timeout=15000)

    page.get_by_text("관련 아이디어").click()
    page.get_by_role("button", name="🌱 이 발명에서 파생 아이디어 만들기").click()

    page.wait_for_selector("text=아이디어 내용", timeout=15000)
    assert parent_memo in page.inner_text("body")  # 파생 배너에 부모 정보가 보인다

    page.locator("textarea").first.fill("파생 테스트용 자식 아이디어")
    page.get_by_role("button", name="저장", exact=True).click()

    page.wait_for_selector("text=부모 발명", timeout=15000)
    assert parent_memo in page.inner_text("body")
