# KooD — 구독 다이어트 플래너

Expo (React Native + TypeScript) + Expo Router.

## 실행
```bash
npm install
npx expo start        # QR → 폰의 Expo Go 앱으로 스캔 / w 키 → 웹 미리보기
npm run typecheck
```

## 폴더
```
src/
  app/                  라우트 (Expo Router)
    _layout.tsx         루트 Stack
    index.tsx           스플래시 → 온보딩/홈 분기
    onboarding.tsx
    (tabs)/             하단 탭: 홈 · 캘린더 · 분석 · 설정
    subscription/new.tsx  구독 추가 (모달)
  components/ui.tsx     공통 UI (버튼, EmptyState, Chip, SegmentedControl …)
  domain/types.ts       데이터 모델
  domain/engine.ts      코어 엔진 (월 환산, 다음 결제일, 해지 권장 기간, 저이용 탐지)
  store/                상태 + 저장소 (AsyncStorage, 추후 API로 교체)
  theme/tokens.ts       디자인 토큰
```

## TODO
- 폰트: 시안이 Pretendard로 보임 → `expo-font`로 로드
- 구독 상세/수정 화면, 캘린더 월간 뷰, 알림(expo-notifications)
- `trackUsage`(이용 기록 대상 여부) 입력 UI — 보험료·통신비 등
