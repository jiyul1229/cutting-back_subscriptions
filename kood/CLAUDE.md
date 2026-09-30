# KooD (구독 다이어트 플래너) — Claude Code 작업 가이드

Expo 관련 규칙은 @AGENTS.md 를 따른다 (SDK 57, Expo Router, `npx expo install` 사용).

## 구조 규칙
- `src/app/` — 라우트(화면)만. 파일 하나 = 화면 하나. 로직 넣지 말 것.
- `src/domain/engine.ts` — 코어 엔진(해지 추천, 결제 주기 계산). **순수 함수만**, React/저장소 import 금지.
- `src/domain/types.ts` — 데이터 모델. 백엔드 API 명세와 일치시킨다.
- `src/store/` — 상태/저장소. `Repository` 인터페이스 뒤에 구현을 숨긴다 (현재 AsyncStorage → 추후 API).
- `src/components/` — 공통 UI. 색·간격은 `src/theme/tokens.ts` 값만 쓰고 하드코딩 금지.

## 기능 ID (PRD)
F1 고정지출 등록/대시보드 · F2 원탭 체크인 · F3 저이용 경고 · F4 해지 캘린더 · F5 유지/해지 태그 · F6 개인화

## 완료 조건
`npx tsc --noEmit` 통과. UI 문구는 한국어 해요체.
