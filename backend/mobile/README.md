# 폰 쪽 이용 기록 코드 (Expo 프로젝트에 복사해서 사용)

이 폴더는 백엔드가 아니라 **Expo 앱 프로젝트에 넣을 코드**입니다.

| 파일 | 역할 |
| --- | --- |
| `modules/usage-stats/` | Android 앱별 사용 시간을 읽는 네이티브 모듈 (Kotlin) |
| `src/usageTracking.ts` | 자동 측정 업로드, 수기 기록, 이용 확인 알림, 결제·해지 기한·주간 기록 알림 예약, "아직 쓰고 있어요" |

## 지원 범위

| 환경 | 자동 측정 | 수기 기록 · 이용 확인 알림 |
| --- | --- | --- |
| Android 개발용 빌드 | 가능 | 가능 |
| Android Expo Go | 불가 (네이티브 모듈 없음) | 가능 |
| iOS | 불가 (스크린타임 데이터를 앱 밖으로 꺼낼 수 없음) | 가능 |
| TV · 태블릿 · PC | 불가 | 가능 |

## 설치

Expo 앱 프로젝트 루트에서:

```bash
# 1. 로컬 모듈 뼈대 생성 (build.gradle 등 자동 생성)
npx create-expo-module@latest --local usage-stats

# 2. 이 폴더의 파일로 덮어쓰기
#    modules/usage-stats/expo-module.config.json
#    modules/usage-stats/index.ts
#    modules/usage-stats/android/src/main/AndroidManifest.xml
#    modules/usage-stats/android/src/main/java/expo/modules/usagestats/UsageStatsModule.kt
#    (뼈대가 만든 ios/ 폴더와 다른 이름의 .kt 파일은 지워도 됩니다)

# 3. 알림 라이브러리
npx expo install expo-notifications

# 4. src/usageTracking.ts 복사
```

## 개발용 빌드 (무료)

Expo Go 대신 우리 앱 전용 Expo Go를 직접 만드는 것입니다. 비용은 들지 않습니다.

- **PC에서 직접 빌드**: Android Studio 설치 → 폰에서 개발자 옵션과 USB 디버깅 켜기 → USB 연결 →
  `npx expo run:android`. 에뮬레이터도 됩니다.
- **클라우드 빌드**: `npx eas build --profile development --platform android` (무료 플랜으로 가능, 대기 시간 있음).
  만들어진 APK를 폰에 설치합니다.

## 백엔드와 연결 순서

1. 구독에 Android 패키지명 연결: `PATCH /api/subscriptions/{id}` `{"android_package": "com.netflix.mediaclient"}`
   패키지명은 Play 스토어 주소의 `id=` 뒤 값입니다.
2. 설정에서 자동 측정 켜기: `setAutoTracking(true)` → 권한 화면에서 앱 허용 → 다시 `setAutoTracking(true)`
3. 앱이 켜질 때 `syncAutoUsage()` 호출 (최근 7일 재전송, 서버가 덮어씀)
4. 앱 시작 시 `scheduleUsageCheck()` 호출 → 매일 설정 시각에 알림 →
   알림을 누르면 `getUsageChecks()` 목록에서 `answerUsageCheck(id, "tv")`
5. 앱 시작 시, 구독을 추가·수정한 뒤, 설정을 바꾼 뒤 `scheduleReminders()` 호출
   → 서버의 `/api/notifications/schedule`을 받아 결제 알림(3일 전), 해지 기한 알림(5일 전),
   "이번 주에 썼나요?"(7일 기록 없음)를 폰에 예약합니다. 여러 번 불러도 중복되지 않습니다.
   expo-notifications의 날짜 예약은 앱이 꺼져 있어도 울립니다. 폰을 재부팅한 뒤에는 앱을 한 번 열면 다시 예약됩니다.
6. 해지 추천 카드의 "아직 쓰고 있어요" 버튼 → `markStillUsing(id)`

자동 측정 날짜는 서버와 같은 한국 시간 기준입니다.
