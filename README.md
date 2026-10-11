# KooD — 구독 다이어트 플래너

Expo (React Native + TypeScript) + Expo Router.

## 실행
```bash
npm install
npx expo start        # QR → 폰의 Expo Go 앱으로 스캔 / w 키 → 웹 미리보기
npm run typecheck
```
서버 주소를 설정하지 않으면 데이터는 폰에만 저장돼요.

## 서버(backend)와 연결해서 실행
### 0. 처음 한 번만: 서버 설치
```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 1. 서버 주소 설정 (`.env.local`)
PowerShell에서 `ipconfig`를 실행해 **Wi-Fi의 IPv4 주소**를 확인하고, 프로젝트 루트에 `.env.local`을 만들어요 (`.env.example` 참고).
```
EXPO_PUBLIC_API_URL=http://<내 PC IP>:8000
```
- 폰에서 `localhost`는 폰 자신을 가리키므로 꼭 PC의 IP를 써야 해요.
- `.env.local`은 git에 올라가지 않아요. 팀원마다 자기 IP로 만들면 돼요.

### 2. 첫 번째 터미널: 서버 켜기
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
`Uvicorn running on http://0.0.0.0:8000`이 나오면 켜진 거예요. 이 창은 닫지 말고 그대로 두세요.

### 3. 두 번째 터미널: 앱 켜기
```powershell
npx expo start
```
QR코드가 나오면 폰의 Expo Go 앱으로 찍으세요. 폰과 PC는 **같은 와이파이**에 연결돼 있어야 해요.

### 4. 연결 확인
- 폰 브라우저에서 `http://<내 PC IP>:8000/health`를 열어 보세요. `{"status":"ok"}`가 보이면 폰이 서버에 닿는 거예요.
- 앱에서 구독을 하나 추가한 뒤 PC 브라우저에서 `http://localhost:8000/docs`를 열어요. `GET /api/subscriptions`에서 "Try it out" → "Execute"를 누르면 방금 추가한 구독이 보여요.

### 안 될 때
- **앱에 "서버에 연결할 수 없어요"가 뜰 때**: 대부분 Windows 방화벽 때문이에요. 서버를 처음 켤 때 "Python 액세스 허용" 창이 뜨면 **개인 네트워크**에 체크하고 허용하세요. 창을 놓쳤다면 관리자 PowerShell에서:
  ```powershell
  New-NetFirewallRule -DisplayName "KooD API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
  ```
- **IP가 바뀌었을 때**: 와이파이를 다시 연결하거나 장소를 옮기면 IP가 바뀔 수 있어요. `ipconfig`로 다시 확인해 `.env.local`을 고친 뒤 `npx expo start`를 껐다가 다시 켜세요.
- **서버 없이 쓰고 싶을 때**: `.env.local`을 지우거나 주소를 비우면 예전처럼 폰에만 저장돼요.

서버 API와 테스트는 [`backend/README.md`](backend/README.md)를 참고하세요.

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
  store/                상태 + 저장소 (기기 저장 localRepository / 서버 apiRepository)
  theme/tokens.ts       디자인 토큰
backend/                FastAPI 서버 (Python)
```

## TODO
- 폰트: 시안이 Pretendard로 보임 → `expo-font`로 로드
- 구독 상세/수정 화면, 캘린더 월간 뷰, 알림(expo-notifications)
- `trackUsage`(이용 기록 대상 여부) 입력 UI — 보험료·통신비 등
