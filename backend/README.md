# 구독 다이어트 플래너 백엔드

Python 3.10+, FastAPI, SQLite, SQLAlchemy 2.x, Pydantic 2.x.
Expo React Native/TypeScript에서 호출하는 single-user MVP입니다.
홈·캘린더·분석은 원천 데이터로 계산하며 화면별 테이블을 만들지 않습니다.

## 발표용 예시 데이터

빈 DB에 예시 구독 8개, 최근 5개월 결제, 최근 90일 이용 기록을 넣습니다(오늘 날짜 기준).

```powershell
py -3 -m app.seed_demo                      # 기본 DB(subscriptions.db)
py -3 -m app.seed_demo --database demo.db   # 다른 DB 파일
```

해지 추천은 넷플릭스·리디셀렉트, 절약 가능 금액은 월 26,900원 / 연 322,800원으로 Figma 시안과 같습니다.
이미 구독이 있으면 넣지 않습니다. 다시 넣으려면 새 DB 파일을 쓰거나 `POST /api/settings/reset-data`로 비웁니다.
서버를 그 DB로 켜려면 `SUBSCRIPTION_DB_PATH`를 같은 파일로 지정합니다.

## 설치와 실행

Windows PowerShell, 프로젝트 루트:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

스마트폰에서도 연결할 개발 서버:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

macOS/Linux는 `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`,
`.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`을 사용합니다.

- 상태 확인: `<Base URL>/health` → `{"status":"ok"}`
- 실행 가능한 API 문서: `<Base URL>/docs`
- 스키마: `<Base URL>/openapi.json`
- 기본 DB: 프로젝트 루트 `subscriptions.db`. 빈 DB는 시작 시 테이블을 만듭니다.
- 이전 DB는 아래 마이그레이션 절차가 필요합니다. 자동 삭제/변환하지 않습니다.
- /health는 서버 응답 확인용이며 DB 상태 검사는 아닙니다.

## Expo 연결과 환경 변수

Base URL에는 /api를 포함하지 않습니다.

| 실행 환경 | Base URL |
| --- | --- |
| 같은 PC의 Expo Web | http://127.0.0.1:8000 |
| 실제 스마트폰 Expo Go/개발 앱 | http://PC-LAN-IP:8000 |
| 같은 PC의 Android Studio 에뮬레이터 | http://10.0.2.2:8000 |
| iOS Simulator | 백엔드 PC의 LAN IP. 같은 Mac에서 백엔드도 실행하면 localhost 가능 |

스마트폰의 127.0.0.1/localhost는 스마트폰 자신입니다. 0.0.0.0은 서버 수신 주소이며 접속 URL이 아닙니다.
PC의 `ipconfig`에서 사용 중인 어댑터의 IPv4를 확인하고 같은 Wi-Fi/LAN에서 폰 브라우저로 /health를 먼저 확인하세요.
연결 실패 시 PC IP 변경, 개인 네트워크의 방화벽 TCP 8000 허용, VPN, 게스트 Wi-Fi/기기 격리를 확인합니다.
인증이 없으므로 신뢰하는 로컬 개발망에서만 실행하고 공유기 포트 포워딩 등으로 공개하지 않습니다.

Expo 서버와 FastAPI는 별도입니다. Expo의 --tunnel은 FastAPI 8000 포트를 자동 공개하지 않습니다.
네이티브 앱은 브라우저 CORS를 적용하지 않습니다. 자체 앱 빌드에서 HTTP가 막히면 Android cleartext/iOS ATS 및 로컬 네트워크 권한을 확인합니다.

백엔드 변수:

| 변수 | 기본값 / 용도 |
| --- | --- |
| CORS_ALLOW_ORIGINS | http://localhost:8081,http://127.0.0.1:8081 |
| SUBSCRIPTION_DB_PATH | 생략 시 프로젝트 루트 subscriptions.db |
| USAGE_EVALUATION_DAYS | 30. data_status의 관찰 기간 기준이며 30/60/90 중 선택 |

```powershell
$env:CORS_ALLOW_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081,http://192.168.0.10:8081"
$env:USAGE_EVALUATION_DAYS = "30"
# 필요한 경우에만 설정. 부모 폴더가 있어야 합니다.
# $env:SUBSCRIPTION_DB_PATH = "C:\path\to\subscriptions.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

변경 후 서버를 완전히 재시작합니다. macOS/Linux는 export로 설정합니다.
.env.example은 참고 파일이며 백엔드는 .env를 자동 로딩하지 않습니다. 별도 settings 라이브러리는 없습니다.
DB 상대 경로는 실행 디렉터리 기준이고 기본 DB 경로는 실행 위치와 무관합니다.

CORS에는 **Web 프론트의 프로토콜+호스트+포트**를 등록합니다. API 주소나 폰 IP가 아닙니다.
설정은 기본 목록을 대체하며 경로/끝의 /, exp://, 와일드카드를 허용하지 않습니다.
빈 값은 교차 Origin 허용을 끕니다. 허용 메서드는 GET/POST/PATCH/DELETE, 추가 허용 헤더는 Content-Type,
쿠키 자격 증명은 OFF입니다. OPTIONS는 미들웨어가 처리합니다.
CORS는 인증이 아니므로 Origin 없는 요청을 차단하지 않습니다.

**프론트 프로젝트**의 .env:

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.0.10:8000
```

Expo는 이 값을 앱에 포함하므로 비밀값을 넣지 않습니다. 변경 후 앱을 완전히 새로고침하세요.
.ts API 모듈에서 `process.env.EXPO_PUBLIC_API_URL`을 읽고 경로를 붙입니다.
POST/PATCH는 JSON.stringify(body)와 Content-Type: application/json을 사용합니다.
fetch는 404/422에서도 자동으로 throw하지 않으므로 response.ok를 검사합니다.
DELETE 이용 기록 성공은 204이며 본문이 없으므로 response.json()을 호출하지 않습니다.
TypeScript 타입 생성 도구와 실제 프론트 코드는 이번에 추가하지 않았습니다.

## 파일 구조와 역할

```text
app/
  __init__.py
  main.py                 # 앱/CORS/스키마 검사/설정 초기화/라우터 등록
  database.py             # SQLite 경로/엔진/FK/세션
  models.py               # 저장 도메인 5개
  schemas.py              # 요청/응답 계약과 검증
  calculations.py         # 한국 날짜, 관찰 기간 정책, 반복 결제 계산
  auto_payments.py        # 지난 결제일의 결제 기록 자동 생성
  recommendations.py      # 해지 추천 계산 (미사용 + 같은 카테고리 중복)
  decision_state.py       # 구독별 최근 결정(유지/해지/보류 태그)
  migrate.py              # 명시적 백업/변환/검증/교체
  seed_demo.py            # 발표용 예시 데이터
  routers/
    __init__.py
    dependencies.py       # 공통 세션/ID/기간 검증
    subscriptions.py      # 구독 등록/조회/수정
    usage_logs.py         # 자동·수동 이용 기록/집계
    payments.py           # 실제 결제
    decisions.py          # 사용자 결정 이력
    dashboard.py          # 홈 계산
    calendar.py           # 예정+실제 날짜 항목
    analytics.py          # 실제 지출 합계/카테고리
    settings.py           # single-user 설정
    notifications.py      # 알림 후보 조회
tests/
  test_api.py             # 기존 검증 범위/HTTP 서버 fixture
  test_features.py        # 새 화면/계산/마이그레이션 검증
  test_usage_tracking.py  # 이용 시간 자동·수기 기록, 이용 확인, 자동 결제 검증
  test_figma_gaps.py      # 구독 필드, 삭제, 전월 대비, 월별 추이, 해지 추천 검증
  test_frontend_parity.py # 앱 기준 맞춤: 해지 권장 기간, 해지 태그, 메모 부정 표현, 이용 단가, 전체 초기화
mobile/                   # Expo 앱에 복사할 Android 자동 측정 모듈과 호출 코드 (mobile/README.md)
requirements.txt
.env.example
.gitignore
README.md
```

계산을 공유하는 작은 helper와 라우터만 사용합니다. Service/Repository/CQRS 계층은 없습니다.

## 최종 DB 테이블

| 테이블 | 필드 |
| --- | --- |
| subscriptions | id Integer PK, name String, price_won Integer, billing_cycle String, billing_day Integer, billing_month Integer nullable, category String nullable, plan_name String nullable, memo String nullable, started_on Date nullable, status String, notification_enabled Boolean, renewal_reminder_days Integer, include_in_analysis Boolean, track_usage Boolean, android_package String nullable UNIQUE, auto_payment_checked_on Date nullable, deleted_at DateTime nullable, created_at DateTime, updated_at DateTime |
| usage_logs | id Integer PK, subscription_id Integer FK, used_date Date, source String, duration_minutes Integer nullable, device String nullable, memo String nullable, created_at DateTime, updated_at DateTime |
| payment_records | id Integer PK, subscription_id Integer FK, amount_won Integer, paid_date Date, category_snapshot String nullable, source String(manual/auto), created_at DateTime |
| decision_history | id Integer PK, subscription_id Integer FK, decision String, decided_at DateTime, memo String nullable |
| app_settings | id Integer PK(항상 1), notifications_enabled Boolean, recommendation_enabled Boolean, auto_tracking_enabled Boolean, usage_check_enabled Boolean, usage_check_time String(HH:MM) |

Subscription과 UsageLog/PaymentRecord/DecisionHistory는 양방향 1:N 관계입니다.
FK 검사와 가격/주기/상태/결제일/출처/결정/설정 singleton CHECK를 적용합니다.
카테고리는 자유 문자열이며 분류 목록을 DB에 고정하지 않습니다.
이용일, 결제일, 결정 시각에 구독별 조회용 인덱스가 있습니다.
수기·알림 기록은 같은 날 여러 건을 허용합니다. 자동 측정(mobile_auto)만 구독·날짜당 1건으로 제한합니다(부분 UNIQUE).
Calendar/Analytics/EmptyState/Notification 테이블은 없습니다.

## API 목록과 화면 연결

성공 응답은 객체 또는 배열이며 data wrapper가 없습니다.

| 메서드 | 경로 | 용도/성공 코드 |
| --- | --- | --- |
| GET | /health | 상태 확인 200 |
| POST | /api/subscriptions | 구독 생성 201 |
| GET | /api/subscriptions | 전체 목록(ID 오름차순) 200 |
| GET | /api/subscriptions/{id} | 상세 200 |
| PATCH | /api/subscriptions/{id} | 구독/서비스별 설정 수정 200 |
| DELETE | /api/subscriptions/{id} | 구독 삭제(숨김) 204 |
| POST | /api/subscriptions/{id}/restore | 삭제한 구독 되살리기 200 |
| GET | /api/dashboard | 홈 200 |
| GET | /api/calendar?year=2026&month=10 | 캘린더 200 |
| POST | /api/subscriptions/{id}/usage-logs | 이용 기록 201 |
| GET | /api/subscriptions/{id}/usage-logs | 이용일/출처 필터 조회 200 |
| PATCH | /api/usage-logs/{log_id} | 이용일/메모 수정 200 |
| DELETE | /api/usage-logs/{log_id} | 이용 기록 삭제 204, 본문 없음 |
| GET | /api/subscriptions/{id}/usage-summary | 이용 현황 200 |
| POST | /api/usage-logs/sync | 폰 자동 측정 결과 업로드 200 |
| GET | /api/usage-checks | 이용 확인 알림에 띄울 구독 목록 200 |
| POST | /api/subscriptions/{id}/check-ins | 이전 checked_at 입력 호환 경로 201, deprecated |
| POST | /api/subscriptions/{id}/decisions | 결정 기록 201 |
| GET | /api/subscriptions/{id}/decisions | 결정 이력 200 |
| POST | /api/payments | 실제 결제 기록 201 |
| GET | /api/payments | 구독/기간별 실제 결제 조회 200 |
| PATCH | /api/payments/{payment_id} | 금액/결제일 수정 200 |
| DELETE | /api/payments/{payment_id} | 결제 기록 삭제 204 |
| GET | /api/analytics/monthly?year=2026&month=9 | 실제 월 지출 200 |
| GET | /api/analytics/categories?year=2026&month=9 | 카테고리 합계/비율 200 |
| GET | /api/analytics/trend?year=2026&month=9&months=5 | 최근 N개월 실제 지출 200 |
| GET | /api/analytics/recommendations | 해지 추천과 절약 금액 200 |
| GET | /api/notifications | 알림 후보 목록 200 |
| GET | /api/settings | 전체 설정 200 |
| PATCH | /api/settings | 전체 설정 수정 200 |
| POST | /api/settings/reset-data | 전체 초기화 204 (`{"confirm": true}` 필수) |

| Figma 화면 | 사용하는 API |
| --- | --- |
| 홈 Empty/Filled | GET dashboard, 필요 시 GET subscriptions |
| 구독 추가 | POST subscriptions. 취소는 프론트에서 닫기 |
| 구독 상세 | GET/PATCH/DELETE subscriptions/{id}, usage-summary, usage-logs(이용 기록 영역), decisions |
| 지출 분석 Empty/Filled | GET analytics/monthly + trend + categories + recommendations |
| 결제 캘린더 | GET calendar. 선택 날짜는 응답 date로 필터 |
| 알림 Empty/Filled | GET notifications |
| 설정 | GET/PATCH settings |
| 온보딩/스플래시 | 전용 저장/API 없음 |

**구독 삭제는 숨김입니다.** `DELETE /api/subscriptions/{id}`는 status=canceled로 바꾸고 deleted_at을 기록합니다.
목록(`?include_deleted=true`일 때만 포함)·홈·캘린더 예정·알림·추천·이용 확인에서 빠집니다.
결제·이용·결정 기록은 남아서 과거 지출 분석과 캘린더의 실제 결제에 계속 나타납니다.
앱 연결(android_package)은 풀어서 같은 앱을 새 구독에 연결할 수 있습니다.
삭제된 구독은 상세·이용 기록·결제·결정 조회만 되고, 수정과 새 기록 추가는 404입니다.
`POST /{id}/restore`로 되살리면 해지 상태로 목록에 돌아오며, 다시 쓰려면 PATCH로 active로 바꿉니다.

## 구독 계약과 반복 결제

```json
{
  "name": "Netflix",
  "price_won": 17000,
  "billing_cycle": "monthly",
  "billing_day": 31,
  "billing_month": null,
  "category": "OTT",
  "plan_name": "프리미엄 플랜",
  "memo": "가족 공유",
  "started_on": "2023-03-15",
  "status": "active",
  "notification_enabled": true,
  "renewal_reminder_days": 3,
  "include_in_analysis": true,
  "track_usage": true,
  "android_package": "com.netflix.mediaclient"
}
```

필수 입력은 name, price_won, billing_day입니다.
기본값은 monthly/active, notification_enabled=true, renewal_reminder_days=3, include_in_analysis=true입니다.
category, billing_month, plan_name, memo, started_on, android_package는 생략하면 null입니다.
plan_name·memo는 앞뒤 공백을 지우며 최대 500자입니다. started_on은 실제 구독 시작일이며 미래 날짜는 거부합니다.
화면의 "등록일"은 started_on이 있으면 그 값, 없으면 created_at을 보여주면 됩니다.
track_usage(기본 true)는 이용 기록 대상 여부입니다. 보험료·통신비처럼 이용 횟수가 의미 없으면 false로 두며,
그러면 미사용 알림·해지 추천·이용 확인에서 빠집니다. include_in_analysis는 프론트의 "분석 표시"(showSavings) 토글입니다.

- billing_cycle: monthly/yearly. yearly는 billing_month(1~12)가 필수.
- billing_day: 1~31. 연간 규칙은 유효한 월/일 조합이어야 하며 2월 29일은 허용.
- status: active/canceled/paused.
- 금액은 0보다 큰 정수. 문자열/소수/bool을 거부하고 SQLite 64비트 범위를 제한.
- reminder는 0~365 정수. 0은 당일만 갱신 알림 후보.
- bool 설정은 JSON true/false만 허용. 이름은 양쪽 공백 제거, 빈 이름 거부.
- PATCH는 생략한 필드를 유지. category:null은 분류 제거.
- 필수 값의 명시적 null은 거부. monthly 전환 시 billing_month:null을 함께 전송.
- PATCH의 기존 값과 새 값을 합친 전체 결제 규칙도 검증.

응답은 입력 필드 전체 + id, deleted_at, created_at, updated_at, next_renewal_date, d_day입니다.
created_at/updated_at 예: `2026-09-30T10:30:00.123456Z`.
next_renewal_date/d_day는 활성 구독만 계산하고 해지·일시정지·삭제면 null입니다.
latest_decision은 가장 최근 결정(keep/cancel/hold, 없으면 null)입니다. 홈 구독 항목에도 들어 있습니다.
cancel_window_start/cancel_window_end는 해지 권장 기간(다음 결제일 5일 전 ~ 하루 전)이며 활성 구독만 계산합니다.

한국 날짜(UTC+09:00)를 기준으로 계산합니다. 31일이 없는 월은 마지막 날로 보정하고 원래 billing_day는 바꾸지 않습니다.
월간 31일은 2026년 2월 28일, 2028년 2월 29일에 해당합니다.
연간 2월 29일은 비윤년 2월 28일에 해당합니다.
다음 갱신일은 **오늘 포함** 가장 가까운 일자이며 오늘 결제면 d_day=0입니다.
구독 규칙/상태 변경 이력은 아직 저장하지 않으므로 모든 예정 계산은 현재 상태를 기준으로 합니다.

## 홈

```json
{
  "monthly_total_won": 17000,
  "previous_month_paid_won": 15700,
  "change_won": 1300,
  "change_ratio": 0.082803,
  "active_subscription_count": 1,
  "subscriptions": [
    {
      "id": 1, "name": "Netflix", "price_won": 17000,
      "billing_cycle": "monthly", "billing_day": 31, "billing_month": null,
      "category": "OTT", "status": "active",
      "notification_enabled": true, "renewal_reminder_days": 3, "include_in_analysis": true,
      "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
      "next_renewal_date": "2026-09-30", "d_day": 0
    }
  ]
}
```

위 예는 한국 날짜 2026-09-30 기준입니다.
활성 구독만 포함하며 next_renewal_date, id 순으로 정렬합니다.
monthly_total_won은 **현재 활성 구독의 월 환산 합계**입니다(앱의 totalMonthly와 같음).
월간은 요금 그대로, 연간은 요금/12(반올림)를 더합니다. 남은 날짜의 금액만 더하는 것은 아닙니다.
실제 결제 유무와 include_in_analysis는 홈 금액에 영향을 주지 않습니다.
중도 가입/해지 일할 계산은 없으며 실지출과 구분해야 합니다.
**전월 대비**는 이번 달 월 환산 구독료와 지난달 실제 결제 합계(분석 제외·해지·삭제 구독 포함)를 비교합니다.
change_ratio는 비율(0.082803 = 8.3% 증가, 음수면 감소)입니다. 지난달 결제가 없으면 세 값 모두 null입니다.
없으면 total=0, count=0, subscriptions=[]입니다.

## 캘린더

year는 1~9998, month는 1~12입니다. 응답 예:

```json
[
  {"date":"2026-10-31","subscription_id":1,"name":"Netflix","amount_won":17000,"type":"scheduled","payment_id":null},
  {"date":"2026-10-31","subscription_id":1,"name":"Netflix","amount_won":16900,"type":"paid","payment_id":3}
]
```

scheduled는 해당 월의 **오늘 이후(오늘 포함)** 활성 구독 규칙을 계산합니다.
그 달에 같은 구독의 결제 기록(paid)이 이미 있으면 scheduled는 표시하지 않습니다.
paid는 선택한 월의 실제 PaymentRecord이며 과거 날짜/해지/분석 제외 구독도 표시합니다.
현재 규칙으로 과거의 예정 결제를 재구성하지 않습니다. 과거 월은 실제 기록만 반환합니다.
수기 결제가 예정일보다 일찍 기록되면 그 달 scheduled는 사라지고 paid만 남습니다.
정렬은 date, subscription_id, type, payment_id 순이며 없으면 []입니다.
이름은 현재 Subscription.name을 사용하므로 서비스명 변경은 과거 캘린더 표시에도 반영됩니다.

## 이용 기록: 자동 + 수동

```json
{"used_date":"2026-09-29","memo":"TV로 봄"}
```

```json
{"used_date":"2026-09-30","source":"mobile_auto"}
```

source는 manual/mobile_auto/notification, 생략하면 manual.
used_date 생략 시 서버의 한국 날짜인 오늘. 미래 날짜나 null은 거부합니다.
응답 예:

```json
{
  "id": 9, "subscription_id": 1, "used_date": "2026-09-29",
  "source": "manual", "memo": "TV로 봄",
  "created_at": "2026-09-30T01:00:00Z", "updated_at": "2026-09-30T01:00:00Z"
}
```

used_date는 실제 이용일, created_at은 서버에 등록한 시각입니다.
조회는 start_date/end_date(양끝 포함)/source 필터를 지원하며 used_date 내림차순, id 내림차순입니다.
예: `/api/subscriptions/1/usage-logs?start_date=2026-09-01&end_date=2026-09-30&source=manual`.

PATCH는 used_date/memo만 받습니다. memo:null은 메모 제거이며 source와 subscription_id 변경은 422입니다.
자동 기록도 수정/삭제 가능하고 수정해도 생성 시각과 원래 source는 유지합니다.
같은 날 자동/수동 기록 여러 개가 저장되며 현재 집계는 건수입니다. 하루 1회 제한/DB UNIQUE는 없습니다.

이전 /check-ins는 checked_at 입력을 한국 날짜로 바꿔 manual로 저장하는 deprecated 호환 경로입니다.
입력 checked_at의 오프셋이 없으면 기존처럼 UTC로 해석합니다.
**응답은 새 UsageLog 계약이며 checked_at 필드는 제거되었습니다.**
새 프론트는 /usage-logs와 used_date를 사용해야 합니다. 새 생성 시각은 실제 서버 기록 시각입니다.

## 이용 시간: 자동 측정 + 수기 기록

이용 기록에 `duration_minutes`(1~1440, 선택)와 `device`(phone/tablet/tv/pc/other, 선택)가 있습니다.

- 수기: `POST /usage-logs`에 `{"device":"tv","duration_minutes":120}`. source는 manual 또는 notification만 받습니다.
- 자동: 폰(Android)이 앱별 하루 사용 시간을 읽어 `POST /api/usage-logs/sync`로 올립니다.

```json
{"entries":[{"package_name":"com.netflix.mediaclient","used_date":"2026-10-02","duration_minutes":95}]}
```

응답: `{"created":1,"updated":0,"deleted":0,"unmatched_packages":[]}`.
구독의 `android_package`로 어느 구독인지 찾습니다. 한 패키지는 한 구독에만 연결할 수 있고 중복이면 409입니다.
같은 구독·날짜는 덮어쓰고, 0분이면 그날 자동 기록을 지웁니다. 수기·알림 기록은 건드리지 않습니다.
설정 `auto_tracking_enabled=false`이면 409입니다. 연결되지 않은 패키지는 무시하고 unmatched_packages로 알려줍니다.
iOS·TV·태블릿은 자동 측정이 불가능하므로 수기 기록과 이용 확인 알림을 씁니다.

`GET /api/usage-checks`는 이용 확인 알림("오늘 OO 보셨나요?")용 목록입니다.
오늘 수기·알림 기록이 없는 활성 구독을 돌려주고, 폰 자동 측정 시간도 함께 줍니다.
`notifications_enabled`나 `usage_check_enabled`가 꺼져 있으면 items는 []입니다.
알림 시각은 `usage_check_time`(기본 21:00)이며 실제 알림 예약은 폰에서 합니다(mobile/README.md).

## 이용 현황과 계산 정책

- 최근 N일: 한국 날짜 오늘을 포함하여 `today-(N-1)`부터 today까지.
- 최근 7/30/90일과 total은 used_date 기준. 미래 DB 기록은 집계하지 않음.
- 하루에 2건이면 2회. 고유 사용일 수가 아님.
- tracking_started_at은 구독 생성 시각. 그보다 앞선 소급 이용일이 있으면 그 날짜의 한국 자정으로 확장.
- observation_days는 시작 날짜와 오늘 양끝을 포함하며 등록 당일도 1일.
- 오래된 소급 기록을 삭제하면 관찰 시작일이 다시 바뀔 수 있음. 장기간 연속 수집을 증명하는 값은 아님.
- 30일 미만이어도 현재까지의 모든 횟수는 바로 제공.
- previous_30d_usage_count는 관찰 60일 이상에서만 계산: 오늘-59일부터 오늘-30일까지.
- usage_change_30d는 최근 30일 건수 - 이전 30일 건수인 **절대 차이**. 백분율 아님.
- 이전 기간을 판단할 수 없으면 비교 두 필드는 null. 관찰 60일 이상이고 0회면 0.
- cost_per_use_30d는 관찰 30일 이상이고 사용이 1회 이상이며 실제 결제가 있는 경우에만 계산.
  최근 30일 실제 PaymentRecord 합 / 최근 30일 사용 건수, 소수 둘째 자리까지.
  관찰 부족/0회/결제 근거 없음은 null. 현재 구독 요금으로 대체하지 않음.
- 단일 구독의 이용단가는 include_in_analysis 토글과 무관. 이 토글은 전체 지출 분석에만 적용.
- 연간 구독도 실제 결제 월의 지출을 그대로 사용하며 월 환산하지 않음.
- data_status는 observation_days >= USAGE_EVALUATION_DAYS면 sufficient, 아니면 collecting.
  관찰 기간 표시이며 해지/저이용 추천이나 데이터 품질 보증이 아님.

등록 당일 무기록 예:

```json
{
  "subscription_id":1, "observation_days":1,
  "usage_count_7d":0, "usage_count_30d":0, "usage_count_90d":0, "total_usage_count":0,
  "previous_30d_usage_count":null, "usage_change_30d":null, "cost_per_use_30d":null,
  "tracking_started_at":"2026-09-30T01:00:00Z", "data_status":"collecting"
}
```

이용 시간: `usage_minutes_7d`, `usage_minutes_30d`, `total_usage_minutes`는 duration_minutes 합계(없는 기록은 0분).
`cost_per_hour_30d`는 cost_per_use_30d와 같은 조건에서 최근 30일 이용 시간이 있을 때만 계산합니다.

비교/집계 정책은 calculations.py의 USAGE_WINDOWS, COMPARISON_DAYS에 모았습니다.
관찰 판단 기간만 환경 변수 USAGE_EVALUATION_DAYS로 30/60/90을 선택합니다.
필드명에 정해진 7/30/90일 집계는 이 변수와 독립적으로 유지합니다.

## 결제 기록과 지출 분석

POST /api/payments:

```json
{"subscription_id":1,"amount_won":17000,"paid_date":"2026-09-15"}
```

응답은 id, subscription_id, amount_won, paid_date, category_snapshot, created_at입니다.
등록 당시 구독 category를 복사하며 이후 가격/카테고리 변경으로 기존 결제 값이 바뀌지 않습니다.
GET /api/payments는 subscription_id/start_date/end_date 필터를 지원합니다.
목록은 paid_date 내림차순, id 내림차순.

**자동 결제 기록**: 활성 구독의 결제일이 지나면(당일 포함) 구독 요금으로 `source=auto` 기록을 만듭니다.
결제 목록·캘린더·분석·이용 현황 조회와 구독 수정 직전에 실행되며 별도 스케줄러는 없습니다.
앱에 등록한 달의 1일부터 확인하므로, 10월 3일에 등록한 매달 1일 결제 구독은 10월 1일 결제도 기록됩니다.
started_on이 그보다 늦으면 started_on부터 확인하고, 등록 이전 달은 소급하지 않습니다.
같은 결제 주기(월간=같은 달, 연간=같은 해)에
이미 기록이 있으면 건너뜁니다. 일시정지·해지 상태였던 기간은 다시 활성화해도 소급하지 않습니다.
금액이 다르면 PATCH로 고치고, 잘못된 기록은 DELETE합니다. 지운 자동 기록은 다시 생기지 않습니다.
실제 청구를 외부 시스템과 검증하지는 않습니다.

월별 응답: `{"total_won":41800,"previous_total_won":45600,"change_won":-3800,"change_ratio":-0.083333}`.
지난달 지출이 0원이면 change_won/change_ratio는 null입니다.
월별 추이 `GET /api/analytics/trend?year=2026&month=9&months=5`는 선택한 달까지 최근 N개월(1~24, 기본 5)을
오래된 달부터 `[{"year":2026,"month":5,"total_won":48700}, ...]`로 줍니다.
카테고리 응답: `[{"category":"OTT","amount_won":29000,"ratio":0.69378}]`.
ratio는 0~1 비율(최대 소수 6자리)이며 프론트에서 ×100으로 퍼센트를 표시합니다.
분류는 결제의 category_snapshot을 사용하고 미분류는 null입니다.

**현재 include_in_analysis=false인 구독은 모든 기간의 분석에서 제외**합니다.
과거 PaymentRecord 자체는 수정하지 않습니다. 토글을 다시 켜면 과거 분석에도 다시 포함됩니다.
status=canceled/paused라도 분석 포함 토글이 켜져 있으면 과거 실제 결제를 포함합니다.
홈·캘린더·결제 목록은 분석 토글의 영향을 받지 않습니다.
데이터가 없으면 월 응답 total_won=0, 카테고리 응답 []입니다.

## 해지 추천

`GET /api/analytics/recommendations`:

```json
{
  "enabled": true, "monthly_saving_won": 26900, "yearly_saving_won": 322800,
  "items": [
    {"subscription_id": 1, "name": "넷플릭스", "category": "OTT", "price_won": 17000,
     "billing_cycle": "monthly", "reasons": ["low_usage", "duplicate_category"],
     "usage_count_90d": 1, "duplicate_with": [2, 3], "cost_per_use_won": 51000,
     "monthly_saving_won": 17000, "yearly_saving_won": 204000}
  ]
}
```

활성 구독만 대상이며 저장하지 않고 조회할 때마다 계산합니다.

- low_usage: 관찰 30일 이상이고 최근 90일 이용 2회 이하(앱 코어 엔진과 같은 기준). 등록한 지 30일이 안 된 구독은 추천하지 않습니다.
- duplicate_category: 같은 카테고리(앞뒤 공백·대소문자 무시)의 활성 구독이 3개 이상이면
  최근 90일 이용이 가장 적은 1개(같으면 더 비싼 것)만 추천합니다. 2개뿐이면 중복으로 보지 않습니다. 카테고리 null과 etc/기타는 제외.
- negative_memo: 미사용 구독의 이용 기록 메모에 "안 봄", "재미없", "안 씀", "해지" 등이 있으면 덧붙는 이유.
- cost_per_use_won: 월 요금 ÷ (90일 이용 횟수 / 3). 이용 0회면 null. 앱 코어 엔진과 같은 계산입니다.
- track_usage=false 구독과 '해지' 태그(최근 결정이 cancel)를 붙인 구독은 추천하지 않습니다.
- 최근 30일 안에 keep 또는 hold 결정을 기록한 구독은 추천하지 않습니다.
- 절약 금액: 월간은 요금, 연간은 요금/12(반올림)를 한 달 기준으로, 연간 절약은 월간×12 또는 연간 요금.
  응답 상단의 합계가 "이번 달 총 절약 가능 금액 / 연간 최대"입니다.
- 설정 recommendation_enabled=false면 enabled=false와 빈 목록을 줍니다.
- 기준값은 calculations.py의 LOW_USAGE_WINDOW_DAYS, LOW_USAGE_MAX_COUNT, LOW_USAGE_MIN_OBSERVATION_DAYS,
  RECOMMENDATION_SNOOZE_DAYS입니다.

## 사용자 결정 이력

POST /api/subscriptions/1/decisions:

```json
{"decision":"hold","memo":"다음 달에 다시 확인"}
```

keep/cancel/hold/none만 허용합니다(앱의 유지/해지/보류 태그, none은 태그 해제).
none을 기록하면 이력은 남고 latest_decision은 null이 됩니다. 이전 DB의 postpone은 마이그레이션 때 hold로 바꿉니다. decided_at은 서버 UTC 현재 시각입니다.
응답은 id, subscription_id, decision, decided_at, memo.
조회는 decided_at/id 내림차순입니다.
결정 이력은 Subscription.status를 자동 변경하지 않습니다.
cancel 결정만으로 실제 해지되지 않으며 hold가 paused를 뜻하지도 않습니다.
다만 최근 결정이 cancel('해지' 태그)인 구독은 앱과 같이 캘린더 예정·알림·해지 추천·이용 확인에서 뺍니다.
다시 keep이나 hold를 기록하면 돌아옵니다.
상태 변경을 원하면 별도로 PATCH /subscriptions/{id}를 호출합니다.

## 전체 초기화

`POST /api/settings/reset-data`에 `{"confirm": true}`를 보내면 구독·이용 기록·결제·결정을 모두 지웁니다.
설정값은 유지합니다. 되돌릴 수 없으며 confirm이 없거나 false면 422입니다. 앱의 온보딩 완료 여부는 폰에 저장되므로
앱에서 따로 초기화합니다.

## 전체 설정과 알림 범위

GET/PATCH /api/settings:

```json
{"notifications_enabled":true,"recommendation_enabled":true,
 "auto_tracking_enabled":false,"usage_check_enabled":true,"usage_check_time":"21:00"}
```

app_settings의 id=1 행만 사용하며 시작할 때 없으면 기본값으로 만듭니다.
PATCH는 부분 수정이며 명시적 null/문자열 bool은 거부합니다.

GET /api/notifications는 현재 조회 시점의 알림 후보 배열입니다.

- 전체 notifications_enabled=false이면 [].
- active + 서비스별 notification_enabled=true인 구독만 대상.
- renewal: 오늘부터 다음 갱신일까지 0~renewal_reminder_days일(기본 3일)이면 후보(당일 포함).
- cancel_window: renewal이 아니면서 다음 결제일이 1~5일 남았으면 해지 권장 기간 후보.
- recommendation: 해지 추천 대상이면 후보(reasons에 이유). recommendation_enabled=false면 제외.
- '해지' 태그를 붙인 구독은 어떤 알림도 만들지 않습니다.
- 하나의 구독이 여러 종류 후보를 동시에 가질 수 있음.
- 서버는 Push/예약 작업/읽음 처리/발송 이력/중복 발송 방지를 구현하지 않음.

응답 항목은 subscription_id, name, type, next_renewal_date, d_day, reasons입니다.
해당 종류와 관계없는 필드는 null입니다.
추천 OFF는 renewal/cancel_window 후보를 끄지 않습니다.
7일 미사용 알림(no_usage)은 해지 추천 알림과 겹쳐 삭제했습니다. 오래 안 쓴 구독은 recommendation으로 알립니다.
서비스명 숨기기 설정(hide_service_names)은 디자인에 없어 삭제했습니다. 이전 DB는 마이그레이션 때 컬럼을 버립니다.

## Android 자동 감지 연동

자동 사용 기록도 아래 API에 전송합니다.

```http
POST /api/subscriptions/1/usage-logs
Content-Type: application/json

{"used_date":"2026-09-30","source":"mobile_auto"}
```

Android 팀이 나중에 구현할 부분:

1. UsageStatsManager 조회와 사용 정보 접근 권한 안내/동의.
2. 앱 패키지명과 subscription_id 연결. 이 매핑은 이번 DB에 미리 추가하지 않음.
3. 실제 이용 이벤트의 기준, 일자 변환(현재 한국 날짜 계약), 중복 전송 방지/오프라인 재시도.
4. 수정/삭제된 자동 기록을 다시 업로드하지 않도록 클라이언트 동기화 정책.
5. 네이티브 모듈과 Expo development build, 기기 테스트.

Expo Go에는 임의의 네이티브 코드를 추가할 수 없으므로 UsageStatsManager 모듈을 붙일 때는 development build가 필요합니다.
일반 REST API/수동 기록 테스트는 Expo Go로 가능합니다.
현재 source는 클라이언트의 주장입니다. PATCH로 출처 변경은 막지만 인증이 없어서 자동 출처를 보안적으로 증명하지는 못합니다.
관련 공식 문서: [UsageStatsManager](https://developer.android.com/reference/android/app/usage/UsageStatsManager),
[Expo 네이티브 코드](https://docs.expo.dev/workflow/customizing/).

## 공통 API 계약

- snake_case 유지. 날짜는 YYYY-MM-DD, 시각 응답은 UTC ISO 8601 Z(소수 초 가능).
- DB에는 시간대 없는 UTC DateTime. 계산/used_date/관찰일은 한국 날짜.
- paid_date와 used_date는 날짜 전용 문자열이며 시간대로 옮겨 날짜를 바꾸지 않음.
- nullable: billing_month/category/memo/category_snapshot 및 요약·알림의 조건부 값.
- 응답 nullable 필드는 생략하지 않고 null. PATCH 생략과 null의 의미는 다름.
- POST 201, GET/PATCH 200, 이용 기록 DELETE 204.
- 없는 ID 404: `{"detail":"Subscription not found"}` 또는 Usage log not found.
- 검증 오류 422: `{"detail":[{"loc":["body","used_date"],"msg":"...","type":"..."}]}`.
- 기간 역전도 422 detail 배열. 잘못된 enum, 필수 null, 초과 필드를 거부.
- 지원하지 않는 메서드는 405. CORS preflight 거부는 400 텍스트.
- msg 영어 문구를 고정 코드로 비교하지 않고 status와 loc/type을 사용.
- TypeScript의 number는 SQLite 64비트 정수 전체를 정확히 표현하지 못함.
  큰 값이 실제 필요해지면 안전 정수 상한 또는 문자열 계약을 합의해야 함.
- OpenAPI는 PATCH 선택 필드에 null 타입을 표시할 수 있으나 일부 명시적 null은 런타임 검증에서 거부.
- HTTP 오류와 fetch 자체의 네트워크 오류, JSON이 아닌 서버 오류를 구분해야 함.

## 기존 DB 마이그레이션

이번 작업 당시 프로젝트 subscriptions.db는 테이블이 없는 빈 파일임을 확인했습니다.
이 파일을 삭제/초기화하지 않았으며, 실제 사용자 DB에는 테스트나 자동 마이그레이션을 실행하지 않았습니다.
기존 컬럼이 있는 다른 DB는 create_all()로 변경할 수 없어 서버 시작 시 스키마 불일치를 안내합니다.

Alembic은 아직 도입하지 않았습니다. 단일 SQLite/단일 사용자 단계에서 이번 변경만을 위한
명시적 백업·변환 스크립트를 제공하는 것으로 충분하다고 판단했습니다.
여러 환경과 여러 마이그레이션 버전을 운영하게 되면 Alembic 등의 버전 관리로 전환해야 합니다.

절차:

1. Uvicorn과 DB 브라우저 등 DB를 사용하는 모든 프로세스를 종료합니다.
2. 대상 DB 경로를 확인합니다. 빈 새 DB는 아래 변환이 필요 없습니다.
3. 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m app.migrate
# 다른 DB:
.\.venv\Scripts\python.exe -m app.migrate --database "C:\path\to\subscriptions.db"
```

스크립트 동작:

- 원본과 같은 폴더에 `*.backup-<고유값>.db` SQLite 스냅샷을 먼저 보존.
- 새 임시 DB에 새 스키마를 생성하고 기존 ID/FK/금액/기록을 복사.
- 이전 renewal_date 버전은 일 → billing_day, 연간 월 → billing_month로 변환.
- 새 구독 옵션은 true/7/true 기본값.
- 이전 checked_at → 한국 날짜 used_date. source=manual.
- 이전 생성/수정 시각이 따로 없었으므로 created_at/updated_at은 기존 checked_at으로 보존.
  당시 실제 서버 입력 시각은 알 수 없으므로 복원할 수 없음.
- 기존 PaymentRecord 금액/날짜/카테고리 유지, 새 설정은 true/true/false.
- FK/무결성/행 수 검증 성공 후 원본 경로를 새 DB로 교체.
- 알 수 없는 테이블/컬럼/뷰/트리거, 변환 불가능한 데이터, 열린 WAL/journal 또는 파일 변경 감지 시 중단.
  교체 전 오류이면 원본을 유지하고 백업은 남김.

현재 프로젝트의 과거 기본 스키마를 대상으로 합니다. 별도로 추가한 제약/인덱스가 있는 커스텀 DB는 수동 검토가 필요합니다.
원본 백업을 검증 후에도 보관하세요. 되돌릴 때는 서버를 중지하고 새 DB도 보존한 뒤 백업을 원래 경로로 복사합니다.
구버전 백업은 구버전 코드와 함께 사용해야 합니다.
DB 삭제 후 재생성은 기본 절차가 아닙니다. 데이터가 불필요한 개발 환경이라도 삭제보다 다른 SUBSCRIPTION_DB_PATH로 새 DB를 만드는 편이 안전합니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

61개 테스트. 별도 Uvicorn 프로세스와 임시 SQLite로 HTTP 요청을 보내며 원래 프로젝트 DB에는 쓰지 않습니다.
기존 12개 테스트 범위를 유지하고 checked_at → used_date, 추가 응답 필드, DELETE CORS 허용 변경에 맞춰 검증을 수정했습니다.
새 검증은 월말/윤년/연간 갱신, D-day와 정렬, 동일 날짜 예정+실제, 설정/알림 경계,
manual/mobile_auto/notification, 과거일/수정/삭제/필터, 7/30/90일과 30/60일 관찰 경계,
0회 이용단가, 결정과 상태 분리, 분석 제외, 이전 두 스키마 변환과 원본 보호를 포함합니다.
자동 측정 동기화·이용 확인·자동 결제 기록·구독 삭제·전월 대비·월별 추이·해지 추천도 검증합니다.
실제 Android 기기의 사용 시간 측정(mobile/), Expo 화면, 실제 알림은 테스트 대상이 아닙니다.

## 확장/삭제 위치와 남은 문제

- 필드 추가: models.py + schemas.py + 해당 라우터 + 명시적 DB 이전 + 테스트.
- 계산 정책 변경: calculations.py 및 해당 화면 라우터. 테이블은 원천 데이터가 바뀔 때만 추가.
- 하루 1회 정책: usage_logs.py의 쓰기/집계 정책을 정하고 기존 중복 정리·동시 요청 처리를 설계한 뒤 UNIQUE 도입 여부 판단.
- 기능 제거: main.py router 등록 + 해당 router + 전용 schema/테스트 제거.
- 데이터 자체 폐기 시에만 model/relationship과 마이그레이션 변경. 화면 삭제만으로 기록을 삭제하지 않음.
- 공통 dependencies/database/calculations는 다른 기능이 사용하므로 참조를 확인하고 유지.

현재 한계:
- 로그인/권한/사용자 구분 없음. source 자동 감지를 서버가 검증하지 못함.
- 페이지네이션/감사 이력 없음. 수기 기록은 동일 일자 여러 건을 의도적으로 허용.
- 사용 기록 편집의 이전 값은 저장하지 않음. 추적 기간은 소급 기록 수정·삭제에 따라 바뀔 수 있음.
- 구독 상태·가격 변경의 과거 이력 없음. 예정 금액은 현재 규칙의 추정이며 과거 실제 금액은 PaymentRecord만 사용.
- category_snapshot은 결제 등록 당시 분류. 나중에 과거 결제를 입력하면 당시 분류를 자동 복원하지 못함.
- include_in_analysis 변경은 과거 조회 결과에도 적용. 불변 회계 보고서 기능은 아님.
- 환불 기록, 구독 영구 삭제, 알림 읽음/발송 이력 없음.
- 반복 일정은 한국 날짜로 고정. 해외 사용자 시간대, 구독별 청구 시각, 일할 계산은 미지원.
- SQLite의 쓰기 동시성 한계, 의존성 정확한 버전 잠금 부재.

로그인/JWT, Docker, Redis, Cloud, 서버 Push, AI/NLP, 실제 해지 대행, 카드/오픈뱅킹 연동은 구현하지 않았습니다.
Android 자동 측정 모듈과 로컬 알림 코드는 mobile/에 있으며 Expo 앱에 넣어 연결합니다.