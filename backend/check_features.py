"""백엔드 기능 확인 스크립트. 프론트 없이 기능을 하나씩 실행하고 결과를 출력합니다.

    python check_features.py          (backend 폴더에서)

임시 DB로 서버를 따로 띄워서 실제 DB(subscriptions.db)는 건드리지 않습니다.
대학생 한 명이 구독 9개를 쓰는 상황을 만들어 팀 문서의 기능(F1~F6, R1~R3)을 순서대로 확인합니다.
끝에 통과/실패 개수를 보여주고, 실패가 있으면 종료 코드 1로 끝납니다.

주의: 출력되는 검출 결과, 오탐률, 등록 시간, 체크인 횟수, 절약 금액은 이 스크립트가 만든
가짜(데모) 데이터로 계산한 값입니다. 실제 사용자 평가 결과가 아니며 기능이 동작하는지만 보여줍니다.
메모 분석은 키워드(로컬)로 고정해 외부 API를 부르지 않습니다.
"""
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(errors="replace")

from app.calculations import BUSINESS_TZ, today  # noqa: E402

TODAY = today()
passed = 0
failed: list[str] = []


# ---------- 출력 ----------

def section(title: str) -> None:
    print(f"\n=== {title} ===")


def check(ok: bool, title: str, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  [OK]   {title}" + (f": {detail}" if detail else ""))
    else:
        failed.append(title)
        print(f"  [실패] {title}" + (f": {detail}" if detail else ""))


def won(n: int | None) -> str:
    return "-" if n is None else f"{n:,}원"


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# ---------- 서버 ----------

class Server:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kood-check-")
        self.db_path = Path(self.temp.name) / "check.db"
        self.log = open(Path(self.temp.name) / "server.log", "w+", encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "SUBSCRIPTION_DB_PATH": str(self.db_path), "MEMO_ANALYSIS": "keyword"}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "error"],
            cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if self.process.poll() is not None:
                break
            try:
                with urlopen(self.base_url + "/health", timeout=0.5):
                    return
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(0.1)
        self.log.seek(0)
        startup_log = self.log.read()
        self.stop()  # 시작에 실패해도 서버와 임시 폴더를 정리합니다.
        raise RuntimeError("서버를 띄우지 못했어요:\n" + startup_log)

    def stop(self) -> list[str]:
        """서버를 끄고 임시 DB·폴더를 지웁니다. 서버 로그의 오류 줄을 돌려줍니다."""
        if self.process.poll() is None:
            if os.name == "nt":
                # 가상환경 python.exe는 실제 서버를 자식으로 띄우므로 자식까지 끕니다.
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        errors = []
        if not self.log.closed:
            self.log.seek(0)
            errors = [line for line in self.log.read().splitlines() if "Traceback" in line or "ERROR" in line]
            self.log.close()
        # Windows는 프로세스가 끝난 직후 잠깐 파일을 잠글 수 있어 '사용 중'일 때만 5초까지 다시 시도합니다.
        for attempt in range(25):
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if attempt == 24:
                    raise
                time.sleep(0.2)
        return errors


server: Server


def api(method: str, path: str, body=None, expect: int | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = Request(server.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            status, raw = response.status, response.read()
    except HTTPError as error:
        status, raw = error.code, error.read()
    result = json.loads(raw) if raw else None
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} → {status} (기대 {expect}): {raw[:300]!r}")
    return result if expect is not None else (status, result)


def subscription(name, price, day=None, **extra):
    body = {"name": name, "price_won": price, **extra}
    if day is not None:
        body["billing_day"] = day
    return api("POST", "/api/subscriptions", body, 201)


def use(sid, when=0, **extra):
    """when일 전 이용 기록(0이면 오늘)."""
    return api("POST", f"/api/subscriptions/{sid}/usage-logs", {"used_date": days_ago(when), **extra}, 201)


def recommendations():
    return api("GET", "/api/analytics/recommendations", expect=200)


def reason_text(item) -> str:
    names = {"low_usage": "저이용", "duplicate_category": "같은 카테고리 중복", "negative_memo": "부정 메모"}
    parts = [names[r] for r in item["reasons"]]
    basis = f"최근 {item['window_days']}일 이용 {item['recent_usage_count']}회"
    if item["cost_per_use_won"]:
        basis += f", 이용 단가 {won(item['cost_per_use_won'])}/회"
    return f"{item['name']} ({' + '.join(parts)}; {basis})"


# ---------- 시나리오 ----------

def run():
    s: dict[str, dict] = {}

    section("F1 고정지출 등록 / 대시보드")
    presets = api("GET", "/api/presets", expect=200)
    check(len(presets) == 10, "주요 서비스 프리셋 10개", ", ".join(p["name"] for p in presets))
    preset = {p["name"]: p for p in presets}

    def from_preset(name, day, seconds):
        p = preset[name]
        return subscription(p["name"], p["price_won"], day, category=p["category"], plan_name=p["plan_name"],
                            android_package=p["android_package"], registration_seconds=seconds)

    s["넷플릭스"] = from_preset("넷플릭스", 15, 18)
    s["유튜브"] = from_preset("유튜브 프리미엄", 22, 25)
    s["티빙"] = from_preset("티빙", 8, 31)
    s["멜론"] = from_preset("멜론", 12, 22)
    next_month = TODAY.month % 12 + 1
    s["클라우드"] = subscription("클라우드 백업", 120000, 10, billing_cycle="yearly", billing_month=next_month,
                              category="cloud", registration_seconds=40)
    s["신문"] = subscription("주간 신문", 3000, billing_cycle="weekly", billing_weekday=0, category="news")
    s["통신비"] = subscription("통신비", 55000, 25, category="etc", track_usage=False)
    s["운동"] = subscription("운동 앱", 9900, 5, category="fitness")
    s["독서"] = subscription("독서 앱", 9900, 18, category="study")
    check(True, "구독 9개 등록 (월간·연간·매주, 프리셋 4개, 통신비는 이용 추적 안 함)")

    netflix = s["넷플릭스"]
    check(netflix["next_renewal_date"] is not None and netflix["cancel_window_start"] is not None,
          "필수 3필드(이름·금액·갱신일)로 등록 → 다음 결제일·해지 권장 기간 자동 계산",
          f"넷플릭스 다음 결제 {netflix['next_renewal_date']} (D-{netflix['d_day']}), "
          f"해지 권장 {netflix['cancel_window_start']} ~ {netflix['cancel_window_end']}")
    api("POST", "/api/subscriptions", {"name": "x", "price_won": 1000}, 422)
    api("POST", "/api/subscriptions", {"name": "x", "price_won": -5, "billing_day": 1}, 422)
    check(True, "잘못된 입력 거부 (갱신일 없음, 음수 금액 → 422)")

    dash = api("GET", "/api/dashboard", expect=200)
    monthly = (sum(x["price_won"] for k, x in s.items() if k not in ("클라우드", "신문"))
               + round(120000 / 12) + round(3000 * 52 / 12))
    yearly = (sum(x["price_won"] for k, x in s.items() if k not in ("클라우드", "신문")) * 12 + 120000 + 3000 * 52)
    check(dash["monthly_total_won"] == monthly and dash["yearly_total_won"] == yearly,
          "월·연 환산 합계 (연간 ÷12, 매주 ×52÷12)",
          f"월 {won(dash['monthly_total_won'])} / 연 {won(dash['yearly_total_won'])}")
    order = [x["name"] for x in dash["subscriptions"]]
    dues = [x["next_renewal_date"] for x in dash["subscriptions"]]
    check(dues == sorted(dues), "홈 목록은 다음 결제일(D-day) 순", " → ".join(order[:5]) + " …")
    by_price = [x["name"] for x in api("GET", "/api/subscriptions?sort=price&order=desc", expect=200)]
    ott = [x["name"] for x in api("GET", "/api/subscriptions?category=ott", expect=200)]
    check(ott == ["넷플릭스", "유튜브 프리미엄", "티빙"], "정렬·필터",
          f"비싼 순 {by_price[:3]}, OTT만 {ott}")
    edited = api("PATCH", f"/api/subscriptions/{s['독서']['id']}", {"renewal_reminder_days": 7, "memo": "시험기간용"}, 200)
    check(edited["renewal_reminder_days"] == 7, "수정 (결제 알림을 7일 전으로)")

    # 이용 기록 쌓기: 오래된 기록이 있으면 그날부터 관찰한 것으로 봅니다(소급 기록).
    use(s["넷플릭스"]["id"], 100)
    use(s["넷플릭스"]["id"], 20, memo="요즘 재미없어서 안 봄", device="tv", duration_minutes=50)
    use(s["유튜브"]["id"], 100)
    for d in range(0, 90, 3):
        use(s["유튜브"]["id"], d, device="phone", duration_minutes=30)
    use(s["티빙"]["id"], 100)
    for d in (2, 9, 20, 33, 47, 58, 70, 85):
        use(s["티빙"]["id"], d, device="tablet")
    use(s["멜론"]["id"], 95)
    use(s["클라우드"]["id"], 120)
    for d in (5, 30, 60, 80):
        use(s["클라우드"]["id"], d)
    use(s["운동"]["id"], 44)                       # 45일 관찰에 1회
    use(s["독서"]["id"], 44)
    use(s["독서"]["id"], 10)                       # 45일 관찰에 2회

    section("F2 원탭 체크인 / 이용 기록")
    tap = api("POST", f"/api/subscriptions/{s['티빙']['id']}/usage-logs", {}, 201)
    check(tap["used_date"] == TODAY.isoformat() and tap["source"] == "manual", "원탭 체크인 (본문 없이 한 번)",
          f"티빙 {tap['used_date']} 기록")
    noti = use(s["유튜브"]["id"], source="notification")
    check(noti["source"] == "notification", "알림 버튼 \"오늘 썼어요\"로 기록")
    api("POST", f"/api/subscriptions/{s['넷플릭스']['id']}/usage-logs", {"used_date": (TODAY + timedelta(days=1)).isoformat()}, 422)
    check(True, "미래 날짜 기록 거부 (422)")
    api("PATCH", "/api/settings", {"auto_tracking_enabled": True}, 200)
    sync = api("POST", "/api/usage-logs/sync", {"entries": [
        {"package_name": preset["유튜브 프리미엄"]["android_package"], "used_date": TODAY.isoformat(), "duration_minutes": 35},
        {"package_name": "com.example.unknown", "used_date": TODAY.isoformat(), "duration_minutes": 10}]}, 200)
    check(sync["created"] == 1 and sync["unmatched_packages"] == ["com.example.unknown"],
          "Android 자동 이용 기록 업로드", f"{sync['created']}건 저장, 연결 안 된 앱 {sync['unmatched_packages']}")
    api("POST", "/api/payments", {"subscription_id": s["유튜브"]["id"], "amount_won": 14900, "paid_date": days_ago(5)}, 201)
    summary = api("GET", f"/api/subscriptions/{s['유튜브']['id']}/usage-summary", expect=200)
    check(summary["usage_count_90d"] > 30 and summary["cost_per_use_30d"] is not None, "이용 현황·이용 단가",
          f"유튜브 7일 {summary['usage_count_7d']}회 / 30일 {summary['usage_count_30d']}회 / 90일 {summary['usage_count_90d']}회, "
          f"7일 {summary['usage_minutes_7d']}분, 이용 단가 {summary['cost_per_use_30d']}원/회")
    checks = api("GET", "/api/usage-checks", expect=200)
    names = [i["name"] for i in checks["items"]]
    check("통신비" not in names and "티빙" not in names, "\"오늘 이용하셨나요?\" 목록 (오늘 기록한 티빙·통신비 제외)",
          ", ".join(names))
    weekly = [n for n in api("GET", "/api/notifications", expect=200) if n["type"] == "weekly_check"]
    check(any(n["name"] == "멜론" for n in weekly), "\"이번 주에 썼나요?\" (7일 이상 기록 없음)",
          ", ".join(f"{n['name']} {n['days_without_record']}일째" for n in weekly))

    section("F3 저이용 경고 (규칙 + 근거)")
    rec = recommendations()
    items = {i["name"]: i for i in rec["items"]}
    for item in rec["items"]:
        print(f"         - {reason_text(item)}")
    nf = items.get("넷플릭스")
    check(nf is not None and set(nf["reasons"]) == {"low_usage", "negative_memo", "duplicate_category"},
          "넷플릭스: 90일 1회 + 부정 메모 + OTT 3개 중 가장 덜 씀")
    check("멜론" in items and items["멜론"]["recent_usage_count"] == 0, "멜론: 90일 0회")
    check("유튜브 프리미엄" not in items and "티빙" not in items and "클라우드 백업" not in items,
          "자주 쓰는 구독은 경고 안 함 (유튜브·티빙·클라우드)")
    check("통신비" not in items, "이용 추적 안 하는 통신비는 경고 0건 (성공 기준 4)")
    collecting = [c["name"] for c in rec["collecting"]]
    check("주간 신문" in collecting, "등록 직후 구독은 \"데이터 수집 중\"",
          ", ".join(f"{c['name']} {c['observation_days']}/{c['needed_days']}일" for c in rec["collecting"]))
    check("운동 앱" in items and items["운동 앱"]["window_days"] == 45 and "독서 앱" not in items,
          "관찰 기간이 짧으면 비율로 환산 (45일 1회 → 경고, 45일 2회 → 아님)")
    check(rec["monthly_saving_won"] == sum(i["monthly_saving_won"] for i in rec["items"]),
          "절약 가능 금액", f"월 {won(rec['monthly_saving_won'])} / 연 {won(rec['yearly_saving_won'])}")

    section("F4 해지 캘린더 / 알림")
    cal = []
    for month_offset in (0, 1):
        y, m = TODAY.year + (TODAY.month - 1 + month_offset) // 12, (TODAY.month - 1 + month_offset) % 12 + 1
        cal += api("GET", f"/api/calendar?year={y}&month={m}", expect=200)
    kinds = {k: sum(1 for r in cal if r["type"] == k) for k in ("paid", "scheduled", "cancel_deadline")}
    deadlines = [r for r in cal if r["type"] == "cancel_deadline"]
    check(all(date.fromisoformat(r["renewal_date"]) - date.fromisoformat(r["date"]) == timedelta(days=1) for r in deadlines)
          and deadlines, "캘린더: 결제 예정·실제 결제·해지 기한(결제 하루 전)",
          f"이번 달~다음 달 예정 {kinds['scheduled']}건, 결제됨 {kinds['paid']}건, 해지 기한 {kinds['cancel_deadline']}건; "
          + ", ".join(f"{r['name']} {r['date'][5:]}까지" for r in deadlines[:3]))
    check(not any(r["type"] == "cancel_deadline" and r["subscription_id"] == s["통신비"]["id"] for r in cal),
          "통신비는 해지 기한 없이 결제일만 (R2)")
    schedule = api("GET", "/api/notifications/schedule?days=30", expect=200)
    check(schedule and all(datetime.fromisoformat(i["fire_at"]) > datetime.now(BUSINESS_TZ) for i in schedule)
          and len({i["id"] for i in schedule}) == len(schedule),
          "폰에 예약할 알림 일정 (지난 시각 없음, 중복 없음)",
          f"30일 {len(schedule)}건; " + ", ".join(f"{i['name']} {i['type']} {i['fire_at'][5:16]}" for i in schedule[:3]))
    check({i["type"] for i in schedule if i["subscription_id"] == s["통신비"]["id"]} <= {"renewal"},
          "통신비는 결제 알림만 (R2)")
    api("PATCH", f"/api/subscriptions/{s['넷플릭스']['id']}", {"notification_enabled": False}, 200)
    off_one = [i for i in api("GET", "/api/notifications/schedule", expect=200) if i["subscription_id"] == s["넷플릭스"]["id"]]
    api("PATCH", f"/api/subscriptions/{s['넷플릭스']['id']}", {"notification_enabled": True}, 200)
    api("PATCH", "/api/settings", {"notifications_enabled": False}, 200)
    off_all = api("GET", "/api/notifications/schedule", expect=200)
    api("PATCH", "/api/settings", {"notifications_enabled": True}, 200)
    check(off_one == [] and off_all == [], "알림 끄기 (서비스별 / 전체)", "넷플릭스만 끔 → 0건, 전체 끔 → 0건")

    section("F5 유지 / 해지 / 보류 태그")
    mid = s["멜론"]["id"]
    api("POST", f"/api/subscriptions/{mid}/decisions", {"decision": "cancel", "memo": "이번 달에 끊기"}, 201)
    gone = "멜론" not in {i["name"] for i in recommendations()["items"]} and \
        all(n["subscription_id"] != mid for n in api("GET", "/api/notifications", expect=200))
    check(gone, "'해지' 태그 → 추천·알림에서 빠짐")
    api("POST", f"/api/subscriptions/{mid}/decisions", {"decision": "none"}, 201)
    detail = api("GET", f"/api/subscriptions/{mid}", expect=200)
    history = api("GET", f"/api/subscriptions/{mid}/decisions", expect=200)
    check(detail["latest_decision"] is None and len(history) == 2, "태그 해제 (이력은 남음)",
          " → ".join(h["decision"] for h in reversed(history)))
    api("POST", f"/api/subscriptions/{s['운동']['id']}/decisions", {"decision": "keep"}, 201)
    check("운동 앱" not in {i["name"] for i in recommendations()["items"]}, "'유지' 태그 → 30일 동안 다시 묻지 않음")

    section("F6 개인화 (\"아직 쓰고 있어요\")")
    feedback = api("POST", f"/api/subscriptions/{s['넷플릭스']['id']}/recommendation-feedback", {"response": "still_using"}, 200)
    after = {i["name"]: i for i in recommendations()["items"]}
    check("넷플릭스" not in after and "duplicate_category" in after.get("티빙", {}).get("reasons", []),
          "넷플릭스에 \"아직 쓰고 있어요\" → 이 구독 기준만 낮추고, OTT 중복은 다음으로 덜 쓰는 티빙으로",
          f"적용 {feedback['applied']}, 이후 추천 {list(after)}")
    metrics = api("GET", "/api/metrics?weeks=4", expect=200)
    api("DELETE", f"/api/subscriptions/{s['넷플릭스']['id']}/recommendation-feedback", expect=204)
    check("넷플릭스" in {i["name"] for i in recommendations()["items"]}, "개인화 기준 초기화 → 다시 추천")
    api("PATCH", "/api/settings", {"low_usage_window_days": 30, "low_usage_max_count": 0}, 200)
    strict = recommendations()
    api("PATCH", "/api/settings", {"low_usage_window_days": 90, "low_usage_max_count": 2}, 200)
    check(all(i["window_days"] <= 30 for i in strict["items"]), "저이용 기준을 사용자가 변경 (30일 0회)",
          f"추천 {[i['name'] for i in strict['items']]}")

    section("R1·R3 판단 지표 (데모 데이터로 계산한 값, 실제 사용자 평가 아님)")
    check(metrics["registration_seconds_avg"] is not None and metrics["false_positive_rate"] is not None,
          "등록 시간·주당 체크인·오탐률 지표가 계산됨",
          f"등록 평균 {metrics['registration_seconds_avg']}초 (중앙값 {metrics['registration_seconds_median']}초), "
          f"주당 체크인 {metrics['checkins_per_week_avg']}회, 경고 {metrics['warnings_shown']}건 중 "
          f"\"아직 쓰고 있어요\" {metrics['still_using_count']}건 → 오탐률 {metrics['false_positive_rate']}")
    log = use(s["티빙"]["id"], memo="이번 달은 거의 못 봤네 안 씀")
    edited = api("PATCH", f"/api/usage-logs/{log['id']}", {"memo": "가족이랑 재밌게 봄"}, 200)
    check(log["memo_negative"] is True and edited["memo_negative"] is False, "메모 분석 (키워드, 로컬)",
          f"\"안 씀\" → 부정 / 고친 메모 → 아님 (분석 방식 {edited['memo_analyzed_by']})")
    api("DELETE", f"/api/usage-logs/{log['id']}", expect=204)

    section("결제 기록 / 지출 분석")
    prev_year, prev_month = (TODAY.year, TODAY.month - 1) if TODAY.month > 1 else (TODAY.year - 1, 12)
    for key in ("넷플릭스", "유튜브", "티빙", "멜론"):
        api("POST", "/api/payments", {"subscription_id": s[key]["id"], "amount_won": s[key]["price_won"],
                                      "paid_date": date(prev_year, prev_month, 10).isoformat()}, 201)
    payments = api("GET", "/api/payments", expect=200)
    auto = [p for p in payments if p.get("source") == "auto"]
    check(len(payments) >= 5, "결제 기록 (수기 + 결제일 지나면 자동 기록)", f"전체 {len(payments)}건, 자동 {len(auto)}건")
    m = api("GET", f"/api/analytics/monthly?year={TODAY.year}&month={TODAY.month}", expect=200)
    cats = api("GET", f"/api/analytics/categories?year={prev_year}&month={prev_month}", expect=200)
    trend = api("GET", f"/api/analytics/trend?year={TODAY.year}&month={TODAY.month}&months=3", expect=200)
    check(abs(sum(c["ratio"] for c in cats) - 1) < 1e-3, "월 지출·카테고리 비중·추이",
          f"이번 달 {won(m['total_won'])} (지난달 {won(m['previous_total_won'])}), 지난달 비중 "
          + ", ".join(f"{c['category']} {c['ratio'] * 100:.0f}%" for c in cats)
          + "; 추이 " + " → ".join(won(t["total_won"]) for t in trend))
    dash = api("GET", "/api/dashboard", expect=200)
    check(dash["previous_month_paid_won"] is not None, "홈 전월 대비",
          f"지난달 결제 {won(dash['previous_month_paid_won'])}, 차이 {won(dash['change_won'])}")

    section("삭제 / 되살리기 / 전체 초기화")
    nid = s["신문"]["id"]
    api("DELETE", f"/api/subscriptions/{nid}", expect=204)
    hidden = nid not in [x["id"] for x in api("GET", "/api/subscriptions", expect=200)]
    restored = api("POST", f"/api/subscriptions/{nid}/restore", expect=200)
    check(hidden and restored["deleted_at"] is None, "삭제하면 숨김, 되살리기 가능")
    status, _ = api("GET", "/api/subscriptions/99999")
    check(status == 404, "없는 구독 → 404")
    api("POST", "/api/settings/reset-data", {"confirm": False}, 422)
    api("POST", "/api/settings/reset-data", {"confirm": True}, 204)
    left = api("GET", "/api/subscriptions?include_deleted=true", expect=200)
    check(left == [], "전체 초기화 (확인값 없으면 거부)")


def check_demo_data():
    section("발표용 데모 데이터")
    from sqlalchemy import URL, create_engine, event
    from sqlalchemy.orm import Session
    from app.database import enable_foreign_keys
    from app.models import AppSettings, Base
    from app.recommendations import evaluate
    from app.seed_demo import seed

    with tempfile.TemporaryDirectory(prefix="kood-demo-") as temp:
        engine = create_engine(URL.create("sqlite", database=str(Path(temp) / "demo.db")))
        try:
            event.listen(engine, "connect", enable_foreign_keys)
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                db.add(AppSettings(id=1))
                seed(db, TODAY)
                db.commit()
                items, _ = evaluate(db, TODAY)
        finally:
            engine.dispose()  # 연결을 닫아야 Windows에서 임시 폴더를 지울 수 있습니다.
    names = sorted(i.name for i in items)
    saving = sum(i.monthly_saving_won for i in items)
    check(names == ["넷플릭스", "리디셀렉트"] and saving == 26900, "Figma 시안과 같은 해지 추천",
          f"{names}, 월 {won(saving)} / 연 {won(saving * 12)}")


def main():
    global server
    print(f"KooD 백엔드 기능 확인 (오늘 {TODAY}, 한국 날짜 기준)")
    print("※ 출력되는 수치는 이 스크립트가 만든 데모 데이터로 계산한 값이며, 실제 사용자 평가 결과가 아닙니다.")
    try:
        server = Server()
    except Exception as error:  # 서버를 못 띄우면 더 확인할 수 없음
        print(f"  [실패] {error}")
        sys.exit(1)
    print(f"임시 서버 {server.base_url} (실제 DB는 건드리지 않음)")
    server_errors: list[str] = []
    try:
        run()
    except Exception as error:  # 중간에 멈춰도 결과 요약과 정리는 합니다.
        failed.append(f"{type(error).__name__}: {error}")
        print(f"  [실패] 확인 도중 멈춤: {type(error).__name__}: {error}")
    finally:
        server_errors = server.stop()
    try:
        check_demo_data()
    except Exception as error:
        failed.append(f"데모 데이터: {type(error).__name__}: {error}")
        print(f"  [실패] 데모 데이터 확인 도중 멈춤: {type(error).__name__}: {error}")
    section("결과")
    check(not server_errors, "서버 오류 로그 없음", "; ".join(server_errors[:3]))
    print(f"\n통과 {passed}개, 실패 {len(failed)}개")
    for title in failed:
        print(f"  - {title}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
