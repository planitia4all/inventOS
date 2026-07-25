from __future__ import annotations

from src.similarity.tfidf import calculate_similarity


def test_similarity_of_identical_text_is_high():
    score = calculate_similarity(
        "금속 핀을 먼저 배열하고 유리를 성형한다",
        "금속 핀을 먼저 배열하고 유리를 성형한다",
        "",
    )
    assert score > 80


def test_similarity_of_unrelated_text_is_low():
    score = calculate_similarity(
        "금속 핀을 먼저 배열하고 유리를 성형하는 관통전극 기술",
        "요리용 프라이팬 코팅 방법",
        "테프론 코팅을 이용한 프라이팬 제조",
    )
    assert score < 50


def test_similarity_with_empty_text_is_zero():
    assert calculate_similarity("", "제목", "초록") == 0.0
    assert calculate_similarity("아이디어", "", "") == 0.0
