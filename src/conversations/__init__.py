"""Conversation Engine — AI 대화를 발명 기록으로 바꾸는 계층.

0.5.0 0단계(데이터 계약)만 구현되어 있다. Parser·Service·UI는 아직 없다.

- `analysis_schema` : analysis_json의 유일한 계약 계층 (키 문자열이 여기만 있다)
- `hashing`         : 원문/메시지 해시, item_id, 중복 판정, 원문 위치 찾기
- `constants`       : UAT로 조정할 임계값·가중치

설계 문서: `docs/conversation-engine-design.md`
"""
