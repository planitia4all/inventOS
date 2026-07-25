"""TF-IDF 기반 유사도 계산.

AI API가 설정되지 않아도 항상 동작하는 기본 유사도 계산 방식이다.
법률적 판단이 아니라 검색 결과 정렬 보조용 참고 점수(0~100)를 제공한다.
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def calculate_similarity(
    invention_text: str, patent_title: str, patent_abstract: str
) -> float:
    """내 아이디어 텍스트와 특허 제목+초록 사이의 코사인 유사도를 0~100으로 반환한다."""
    invention_text = (invention_text or "").strip()
    patent_text = f"{patent_title or ''} {patent_abstract or ''}".strip()

    if not invention_text or not patent_text:
        return 0.0

    try:
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform([invention_text, patent_text])
    except ValueError:
        # 두 텍스트 모두 stopword뿐이거나 공백만 있는 등 벡터화가 불가능한 경우
        return 0.0

    score = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
    return round(float(score) * 100, 1)
