"""팀 문서(PRD·위험·성공 기준)와 맞춘 기능 검증.

캘린더 해지 기한, 매주 결제, 알림 예약 일정, 이번 주 기록 확인, 통신비·보험료 예외, 프리셋, 지표,
"아직 쓰고 있어요" 민감도 조정, 데이터 수집 중, 메모 분석(AI/키워드), 목록 정렬·필터.
"""
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session

from app import memo_analysis
from app.auto_payments import ensure_auto_payments
from app.calculations import BUSINESS_TZ, monthly_amount, next_renewal, scheduled_dates, today, yearly_amount
from app.database import enable_foreign_keys
from app.models import AppSettings, Base, DecisionHistory, PaymentRecord, Subscription
from app.routers.calendar import get_calendar
from test_api import LiveApiTestCase


def kst_datetime(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(BUSINESS_TZ)


class DocAlignmentApiTests(LiveApiTestCase):
    def setUp(self):
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            for table in ("recommendation_warnings", "decision_history", "usage_logs", "payment_records",
                          "subscriptions"):
                connection.execute(f"DELETE FROM {table}")
            connection.execute(
                "UPDATE app_settings SET notifications_enabled=1, recommendation_enabled=1, usage_check_enabled=1, "
                "usage_check_time='21:00', low_usage_window_days=90, low_usage_max_count=2"
            )

    def age(self, sid, days):
        start = datetime.combine(today() - timedelta(days=days - 1), time.min, BUSINESS_TZ)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE subscriptions SET created_at=? WHERE id=?",
                               (start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(" "), sid))

    def use(self, sid, days_ago=0, **extra):
        return self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {
            "used_date": (today() - timedelta(days=days_ago)).isoformat(), **extra,
        }, 201)

    def recommended(self):
        return {i["subscription_id"]: i for i in self.request("GET", "/api/analytics/recommendations")["items"]}

    def notices(self, sid):
        return [n["type"] for n in self.request("GET", "/api/notifications") if n["subscription_id"] == sid]

    # ---------- 매주 결제 ----------
    def test_weekly_subscription(self):
        weekday = today().weekday()
        weekly = self.create_subscription(name="주간 구독", price_won=3000, billing_cycle="weekly",
                                          billing_day=None, billing_weekday=(weekday + 2) % 7)
        self.assertEqual((weekly["billing_cycle"], weekly["billing_day"], weekly["billing_weekday"]),
                         ("weekly", None, (weekday + 2) % 7))
        self.assertEqual(weekly["d_day"], 2)
        self.assertEqual(
            date.fromisoformat(weekly["cancel_window_end"]) - date.fromisoformat(weekly["cancel_window_start"]),
            timedelta(days=1),  # 매주 결제는 해지 권장 기간 이틀
        )
        dashboard = self.request("GET", "/api/dashboard")
        self.assertEqual(dashboard["monthly_total_won"], round(3000 * 52 / 12))
        self.assertEqual(dashboard["yearly_total_won"], 3000 * 52)
        for bad in (
            {"billing_cycle": "weekly", "billing_day": None},                       # 요일 없음
            {"billing_cycle": "weekly", "billing_weekday": 1},                      # 결제일이 같이 옴
            {"billing_cycle": "weekly", "billing_day": None, "billing_weekday": 7},
            {"billing_weekday": 1},                                                 # 월간인데 요일
        ):
            self.request("POST", "/api/subscriptions", {"name": "x", "price_won": 1, "billing_day": 1, **bad}, 422)
        self.request("POST", "/api/subscriptions", {"name": "x", "price_won": 1}, 422)  # 월간인데 결제일 없음
        # 월간 → 매주로 바꾸려면 결제일을 null로 함께 보냅니다
        monthly = self.create_subscription()
        root = f"/api/subscriptions/{monthly['id']}"
        self.request("PATCH", root, {"billing_cycle": "weekly", "billing_weekday": 0}, 422)
        changed = self.request("PATCH", root, {"billing_cycle": "weekly", "billing_weekday": 0, "billing_day": None})
        self.assertEqual((changed["billing_cycle"], changed["billing_weekday"]), ("weekly", 0))
        back = self.request("PATCH", root, {"billing_cycle": "monthly", "billing_weekday": None, "billing_day": 10})
        self.assertEqual((back["billing_day"], back["billing_weekday"]), (10, None))

    # ---------- 통신비·보험료 예외 ----------
    def test_fixed_expense_gets_only_renewal_reminders(self):
        due = today() + timedelta(days=4)
        if due.month != today().month:
            self.skipTest("월말 경계")
        bill = self.create_subscription(name="통신비", track_usage=False, billing_day=due.day, category="etc")
        detail = self.request("GET", f"/api/subscriptions/{bill['id']}")
        self.assertIsNone(detail["cancel_window_start"])
        self.assertEqual(self.notices(bill["id"]), [])  # D-4: 해지 권장 기간 알림 없음, 결제 알림(3일 전)은 아직
        calendar = self.request("GET", f"/api/calendar?year={due.year}&month={due.month}")
        self.assertEqual([r["type"] for r in calendar if r["subscription_id"] == bill["id"]], ["scheduled"])
        self.age(bill["id"], 30)
        self.assertNotIn("weekly_check", self.notices(bill["id"]))
        schedule = self.request("GET", "/api/notifications/schedule?days=30")
        self.assertEqual({i["type"] for i in schedule if i["subscription_id"] == bill["id"]}, {"renewal"})

    # ---------- 알림 예약 일정 ----------
    def test_reminder_schedule(self):
        due = today() + timedelta(days=10)
        sub = self.create_subscription(billing_day=due.day, price_won=17000)
        schedule = [i for i in self.request("GET", "/api/notifications/schedule?days=20")
                    if i["subscription_id"] == sub["id"]]
        first_due = next_renewal(SimpleNamespace(billing_cycle="monthly", billing_day=due.day, billing_month=None,
                                                 billing_weekday=None), today())
        by_type = {}
        for item in schedule:
            by_type.setdefault(item["type"], []).append(item)
        renewal = by_type["renewal"][0]
        self.assertEqual(renewal["renewal_date"], first_due.isoformat())
        self.assertEqual(kst_datetime(renewal["fire_at"]),
                         datetime.combine(first_due - timedelta(days=3), time(9), BUSINESS_TZ))
        self.assertEqual((renewal["d_day_at_fire"], renewal["amount_won"]), (3, 17000))
        window = by_type["cancel_window"][0]
        self.assertEqual(kst_datetime(window["fire_at"]),
                         datetime.combine(first_due - timedelta(days=5), time(9), BUSINESS_TZ))
        # 등록하고 7일 동안 기록이 없으면 이용 확인 시각(21:00)에 "이번 주에 썼나요?"
        weekly = by_type["weekly_check"][0]
        self.assertEqual(kst_datetime(weekly["fire_at"]),
                         datetime.combine(today() + timedelta(days=7), time(21), BUSINESS_TZ))
        self.assertTrue(all(kst_datetime(i["fire_at"]) > datetime.now(BUSINESS_TZ) for i in schedule))
        self.assertEqual(len({i["id"] for i in schedule}), len(schedule))
        # 기록하면 그날부터 다시 7일
        self.use(sub["id"])
        weekly = [i for i in self.request("GET", "/api/notifications/schedule?days=20")
                  if i["subscription_id"] == sub["id"] and i["type"] == "weekly_check"][0]
        self.assertEqual(kst_datetime(weekly["fire_at"]).date(), today() + timedelta(days=7))
        # 해지 태그·알림 끔이면 없음
        self.request("POST", f"/api/subscriptions/{sub['id']}/decisions", {"decision": "cancel"}, 201)
        self.assertEqual([i for i in self.request("GET", "/api/notifications/schedule")
                          if i["subscription_id"] == sub["id"]], [])
        self.request("PATCH", "/api/settings", {"notifications_enabled": False})
        self.assertEqual(self.request("GET", "/api/notifications/schedule"), [])
        self.request("GET", "/api/notifications/schedule?days=0", expected=422)

    def test_weekly_check_notification(self):
        sid = self.create_subscription()["id"]
        self.age(sid, 8)
        notice = [n for n in self.request("GET", "/api/notifications")
                  if n["subscription_id"] == sid and n["type"] == "weekly_check"]
        self.assertEqual(notice[0]["days_without_record"], 7)
        self.use(sid, 2)
        self.assertNotIn("weekly_check", self.notices(sid))
        self.request("PATCH", "/api/settings", {"usage_check_enabled": False})
        self.age(sid, 30)
        self.assertNotIn("weekly_check", self.notices(sid))

    # ---------- 프리셋 ----------
    def test_presets(self):
        presets = self.request("GET", "/api/presets")
        self.assertEqual(len(presets), 10)
        netflix = next(p for p in presets if p["name"] == "넷플릭스")
        self.assertEqual((netflix["price_won"], netflix["category"]), (17000, "ott"))
        # 프리셋 그대로 등록할 수 있어야 함
        for preset in presets:
            body = {k: v for k, v in preset.items() if v is not None}
            self.request("POST", "/api/subscriptions", {**body, "billing_day": 1}, 201)

    # ---------- 데이터 수집 중 ----------
    def test_collecting(self):
        new = self.create_subscription(name="새 구독")["id"]
        old = self.create_subscription(name="오래된 구독", category="book")["id"]
        self.age(old, 40)
        result = self.request("GET", "/api/analytics/recommendations")
        self.assertEqual([(c["subscription_id"], c["observation_days"], c["needed_days"]) for c in result["collecting"]],
                         [(new, 1, 30)])
        self.assertIn(old, {i["subscription_id"] for i in result["items"]})

    # ---------- "아직 쓰고 있어요" ----------
    def test_still_using_lowers_threshold_for_that_subscription(self):
        sid = self.create_subscription(category="book")["id"]
        self.age(sid, 90)
        self.use(sid, 3)
        self.assertEqual(self.recommended()[sid]["recent_usage_count"], 1)
        feedback = self.request("POST", f"/api/subscriptions/{sid}/recommendation-feedback",
                                {"response": "still_using"})
        self.assertEqual((feedback["applied"], feedback["low_usage_max_count_override"]), (["threshold"], 0))
        self.assertNotIn(sid, self.recommended())  # 1회는 이제 괜찮음
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("DELETE FROM usage_logs WHERE subscription_id=?", (sid,))
        item = self.recommended()[sid]  # 0회로 줄면 다시 추천
        self.assertTrue(item["personalized"])
        self.request("POST", f"/api/subscriptions/{sid}/recommendation-feedback", {"response": "nope"}, 422)
        self.request("DELETE", f"/api/subscriptions/{sid}/recommendation-feedback", expected=204)
        detail = self.request("GET", f"/api/subscriptions/{sid}")
        self.assertIsNone(detail["low_usage_max_count_override"])

    def test_short_observation_is_scaled_to_window(self):
        # 기준 90일 2회. 45일만 봤으면 1회 이하일 때만 추천합니다(성공 기준 6: 첫 달 판단과 90일 기준의 충돌 해소).
        once = self.create_subscription(name="1회", category="book")["id"]
        twice = self.create_subscription(name="2회", category="music")["id"]
        for sid in (once, twice):
            self.age(sid, 45)
        self.use(once, 1)
        self.use(twice, 1)
        self.use(twice, 2)
        items = self.recommended()
        self.assertNotIn(twice, items)  # 90일로 치면 4회
        self.assertEqual((items[once]["recent_usage_count"], items[once]["window_days"]), (1, 45))
        self.assertEqual(items[once]["cost_per_use_won"], 17000 * 45 // 30)  # 월 요금 ÷ 한 달 평균(1 × 30/45)
        # 90일이 지나면 그대로 90일 2회 기준
        self.age(twice, 120)
        self.assertEqual(self.recommended()[twice]["window_days"], 90)

    def test_still_using_after_short_observation_keeps_current_rate(self):
        sid = self.create_subscription(category="book")["id"]
        self.age(sid, 45)
        self.use(sid, 1)
        feedback = self.request("POST", f"/api/subscriptions/{sid}/recommendation-feedback",
                                {"response": "still_using"})
        # 45일 1회 = 90일 2회 빈도. 이보다 줄어야(90일 1회 이하) 다시 추천
        self.assertEqual((feedback["applied"], feedback["low_usage_max_count_override"]), (["threshold"], 1))
        self.assertNotIn(sid, self.recommended())

    def test_still_using_with_zero_uses_snoozes(self):
        sid = self.create_subscription(category="book")["id"]
        self.age(sid, 40)
        feedback = self.request("POST", f"/api/subscriptions/{sid}/recommendation-feedback",
                                {"response": "still_using"})
        self.assertEqual(feedback["applied"], ["snooze"])
        self.assertEqual(feedback["low_usage_snooze_until"], (today() + timedelta(days=90)).isoformat())
        self.assertNotIn(sid, self.recommended())
        # 지금 추천 대상이 아니면 409
        self.request("POST", f"/api/subscriptions/{sid}/recommendation-feedback", {"response": "still_using"}, 409)

    def test_still_using_on_duplicate_moves_to_next_least_used(self):
        ids = {}
        for name, uses in (("a", 9), ("b", 5), ("c", 3)):
            ids[name] = self.create_subscription(name=name, category="ott")["id"]
            for day in range(uses):
                self.use(ids[name], day)
        self.assertEqual(set(self.recommended()), {ids["c"]})
        feedback = self.request("POST", f"/api/subscriptions/{ids['c']}/recommendation-feedback",
                                {"response": "still_using"})
        self.assertEqual(feedback["applied"], ["duplicate_exempt"])
        # c를 계속 쓴다면 남은 것 중 가장 적게 쓰는 b를 추천
        self.assertEqual(set(self.recommended()), {ids["b"]})

    # ---------- 지표 ----------
    def test_metrics(self):
        a = self.create_subscription(name="a", category="book", registration_seconds=20)["id"]
        b = self.create_subscription(name="b", category="shopping", registration_seconds=40)["id"]
        self.create_subscription(name="c", category="study", registration_seconds=90)
        self.request("POST", "/api/subscriptions", {"name": "x", "price_won": 1, "billing_day": 1,
                                                    "registration_seconds": 3601}, 422)
        self.use(a, 0)
        self.use(a, 0, source="notification")
        self.request("PATCH", "/api/settings", {"auto_tracking_enabled": True})
        self.request("PATCH", f"/api/subscriptions/{b}", {"android_package": "com.example.b"})
        self.request("POST", "/api/usage-logs/sync", {"entries": [
            {"package_name": "com.example.b", "used_date": today().isoformat(), "duration_minutes": 30}]})
        metrics = self.request("GET", "/api/metrics?weeks=2")
        self.assertEqual((metrics["registration_count"], metrics["registration_seconds_avg"],
                          metrics["registration_seconds_median"]), (3, 50.0, 40.0))
        self.assertEqual([w["count"] for w in metrics["checkins_by_week"]], [0, 2])  # 자동 측정 제외
        self.assertEqual(metrics["checkins_per_week_avg"], 1.0)
        self.assertIsNone(metrics["false_positive_rate"])

        for sid in (a, b):
            self.age(sid, 40)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("DELETE FROM usage_logs")
        self.assertEqual(set(self.recommended()), {a, b})  # 보여준 순간 경고로 기록
        self.recommended()  # 다시 봐도 경고는 구독마다 하나
        self.request("POST", f"/api/subscriptions/{a}/recommendation-feedback", {"response": "still_using"})
        self.request("POST", f"/api/subscriptions/{b}/decisions", {"decision": "keep"}, 201)
        metrics = self.request("GET", "/api/metrics")
        self.assertEqual((metrics["warnings_shown"], metrics["warnings_answered"], metrics["still_using_count"]),
                         (2, 2, 1))
        self.assertEqual((metrics["false_positive_rate"], metrics["decision_rate"]), (0.5, 0.5))

    # ---------- 메모 분석 결과 저장 ----------
    def test_memo_analysis_is_stored(self):
        sid = self.create_subscription()["id"]
        negative = self.use(sid, memo="요즘 재미없어서 안 봄")
        self.assertEqual((negative["memo_negative"], negative["memo_analyzed_by"]), (True, "keyword"))
        plain = self.use(sid)
        self.assertEqual((plain["memo_negative"], plain["memo_analyzed_by"]), (None, None))
        edited = self.request("PATCH", f"/api/usage-logs/{negative['id']}", {"memo": "가족이랑 재밌게 봄"})
        self.assertEqual(edited["memo_negative"], False)

    # ---------- 목록 정렬·필터 ----------
    def test_list_sort_and_filter(self):
        cheap = self.create_subscription(name="나", price_won=5000, category="book", billing_day=1)["id"]
        pricey = self.create_subscription(name="가", price_won=20000, category="ott", billing_day=2)["id"]
        yearly = self.create_subscription(name="다", price_won=120000, category="ott", billing_cycle="yearly",
                                          billing_month=1, billing_day=1)["id"]  # 월 10,000원
        ids = lambda q: [s["id"] for s in self.request("GET", "/api/subscriptions" + q)]
        self.assertEqual(ids("?sort=price"), [cheap, yearly, pricey])
        self.assertEqual(ids("?sort=price&order=desc"), [pricey, yearly, cheap])
        self.assertEqual(ids("?sort=name"), [pricey, cheap, yearly])
        self.assertEqual(ids("?category=ott"), [pricey, yearly])
        self.assertEqual(ids("?sort=category"), [cheap, pricey, yearly])
        self.request("GET", "/api/subscriptions?sort=bad", expected=422)


class CalendarDeadlineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="calendar-deadline-")
        self.addCleanup(temp.cleanup)
        engine = create_engine(URL.create("sqlite", database=str(Path(temp.name) / "test.db")))
        self.addCleanup(engine.dispose)
        event.listen(engine, "connect", enable_foreign_keys)
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(self.db.close)
        self.db.add(AppSettings(id=1))
        self.db.commit()

    def sub(self, **values):
        item = Subscription(**{"name": "s", "price_won": 1000, "billing_cycle": "monthly", "billing_day": 15,
                               "created_at": datetime(2026, 9, 1), "auto_payment_checked_on": date(2026, 12, 31),
                               **values})
        self.db.add(item)
        self.db.commit()
        return item

    def calendar(self, year, month, on=date(2026, 10, 3)):
        with patch("app.routers.calendar.today", return_value=on):
            return [(r.date, r.subscription_id, r.type, r.renewal_date) for r in get_calendar(year, month, self.db)]

    def test_deadline_is_day_before_renewal(self):
        sub = self.sub()
        self.assertEqual(self.calendar(2026, 10), [
            (date(2026, 10, 14), sub.id, "cancel_deadline", date(2026, 10, 15)),
            (date(2026, 10, 15), sub.id, "scheduled", None),
        ])

    def test_next_month_first_day_deadline_shows_this_month(self):
        sub = self.sub(billing_day=1)
        rows = self.calendar(2026, 10)
        self.assertIn((date(2026, 10, 31), sub.id, "cancel_deadline", date(2026, 11, 1)), rows)

    def test_no_deadline_for_paid_tagged_fixed_or_past(self):
        paid = self.sub(name="paid")
        self.db.add(PaymentRecord(subscription_id=paid.id, amount_won=1000, paid_date=date(2026, 10, 2)))
        tagged = self.sub(name="tagged")
        self.db.add(DecisionHistory(subscription_id=tagged.id, decision="cancel"))
        fixed = self.sub(name="fixed", track_usage=False)
        past = self.sub(name="past", billing_day=2)
        self.db.commit()
        rows = self.calendar(2026, 10)
        self.assertNotIn(tagged.id, [r[1] for r in rows])
        self.assertEqual([r[2] for r in rows if r[1] == paid.id], ["paid"])
        self.assertEqual([r[2] for r in rows if r[1] == fixed.id], ["scheduled"])
        self.assertEqual([r[2] for r in rows if r[1] == past.id], [])

    def test_weekly_calendar_and_auto_payments(self):
        weekly = self.sub(billing_cycle="weekly", billing_day=None, billing_weekday=0,  # 월요일
                          auto_payment_checked_on=None, created_at=datetime(2026, 10, 1, 3))
        mondays = [date(2026, 10, d) for d in (5, 12, 19, 26)]
        self.assertEqual(scheduled_dates(weekly, 2026, 10), mondays)
        self.assertEqual(next_renewal(weekly, date(2026, 10, 5)), date(2026, 10, 5))
        self.assertEqual(next_renewal(weekly, date(2026, 10, 6)), date(2026, 10, 12))
        self.assertEqual((monthly_amount(weekly), yearly_amount(weekly)), (4333, 52000))
        rows = self.calendar(2026, 10)
        self.assertEqual([r[0] for r in rows if r[2] == "scheduled"], mondays)
        self.assertEqual([r[0] for r in rows if r[2] == "cancel_deadline"],
                         [d - timedelta(days=1) for d in mondays])
        with patch("app.auto_payments.today", return_value=date(2026, 10, 20)):
            ensure_auto_payments(self.db)
        paid = [p.paid_date for p in self.db.scalars(select(PaymentRecord).order_by(PaymentRecord.paid_date))]
        self.assertEqual(paid, mondays[:3])


class MemoAnalysisTests(unittest.TestCase):
    def fake_response(self, stop_reason="end_turn", text='{"negative": true, "reason": "안 본다고 함"}'):
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])

    def run_ai(self, response):
        client = MagicMock()
        client.beta.messages.create.return_value = response
        with patch.dict("os.environ", {"MEMO_ANALYSIS": "ai"}), patch("anthropic.Anthropic", return_value=client):
            return memo_analysis.analyze_memo("요즘 손이 안 가"), client

    def test_keyword_by_default(self):
        with patch.dict("os.environ", {"MEMO_ANALYSIS": "keyword"}), \
                patch.object(memo_analysis, "analyze_with_claude") as ai:
            self.assertEqual(memo_analysis.analyze_memo("재미없음"), (True, "keyword"))
            ai.assert_not_called()

    def test_ai_result_and_request_shape(self):
        result, client = self.run_ai(self.fake_response())
        self.assertEqual(result, (True, "ai"))  # 키워드에는 없는 표현도 AI가 판단
        kwargs = client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "요즘 손이 안 가"}])

    def test_ai_failures_fall_back_to_keywords(self):
        for response in (self.fake_response(stop_reason="refusal"), self.fake_response(text="not json"),
                         self.fake_response(text='{"reason": "x"}')):
            result, _ = self.run_ai(response)
            self.assertEqual(result, (False, "keyword"))


if __name__ == "__main__":
    unittest.main()
