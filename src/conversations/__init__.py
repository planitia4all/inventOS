"""Conversation Engine — AI 대화를 발명 기록으로 바꾸는 계층.

0.5.0의 0단계(데이터 계약), 1단계(저장 기반), 2-1단계(Clipboard Parser)까지
구현되어 있다. 중복 판정 연결·AI 호출·본문 반영·UI는 아직 없다.

- `analysis_schema` : analysis_json의 유일한 계약 계층 (키 문자열이 여기만 있다)
- `hashing`         : 원문/메시지/요약 해시, item_id, 중복 판정, 원문 위치 찾기
- `constants`       : UAT로 조정할 임계값·가중치·상태값
- `repository`      : ConversationImport DB 접근 (SQL 쿼리는 여기에만)
- `service`         : 저장·검증·요약 체인 검사·Soft Delete
- `parser`          : 붙여넣은 원문을 메시지 단위로 자르기 (화자·원문 위치)

설계 문서: `docs/conversation-engine-design.md`
"""
