import asyncio
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session

from app import main
from app.calculations import BUSINESS_TZ, next_renewal, scheduled_date, today
from app.database import enable_foreign_keys
from app.migrate import migrate_database
from app.models import AppSettings, Base, PaymentRecord, Subscription, UsageLog
from app.routers.dashboard import get_dashboard
from app.routers.calendar import get_calendar
from app.routers.notifications import notification_candidates
from app.routers.usage_logs import get_usage_summary
from test_api import LiveApiTestCase


class FeatureApiTests(LiveApiTestCase):
    def setUp(self):
        # 이 클래스의 서버만 사용하는 임시 DB입니다. 실제 DB에는 접근하지 않습니다.
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            for table in ("decision_history", "usage_logs", "payment_records", "subscriptions"):
                connection.execute(f"DELETE FROM {table}")
            connection.execute(
                "UPDATE app_settings SET notifications_enabled=1, recommendation_enabled=1, "
                "auto_tracking_enabled=0, usage_check_enabled=1, usage_check_time='21:00'"
            )

    def use(self, sid, days_ago=0, **changes):
        return self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {
            "used_date": (today() - timedelta(days=days_ago)).isoformat(), **changes,
        }, 201)

    def age_subscription(self, sid, observation_days):
        start = datetime.combine(today() - timedelta(days=observation_days - 1), time.min, BUSINESS_TZ)
        stored = start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(" ")
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            # 과거 결제일의 자동 결제 기록은 만들지 않도록 오늘까지 확인한 것으로 둡니다.
            connection.execute("UPDATE subscriptions SET created_at=?, auto_payment_checked_on=? WHERE id=?",
                               (stored, today().isoformat(), sid))

    def test_empty_screens_and_openapi(self):
        self.assertEqual(self.request("GET", "/api/dashboard"), {
            "monthly_total_won": 0, "previous_month_paid_won": None, "change_won": None, "change_ratio": None,
            "active_subscription_count": 0, "subscriptions": [],
        })
        self.assertEqual(self.request("GET", "/api/calendar?year=2026&month=9"), [])
        self.assertEqual(self.request("GET", "/api/analytics/monthly?year=2026&month=9"), {
            "total_won": 0, "previous_total_won": 0, "change_won": None, "change_ratio": None,
        })
        self.assertEqual(self.request("GET", "/api/analytics/categories?year=2026&month=9"), [])
        self.assertEqual(self.request("GET", "/api/notifications"), [])
        self.assertIn("swagger-ui", self.request("GET", "/docs"))
        paths = self.request("GET", "/openapi.json")["paths"]
        for path in ("/api/dashboard", "/api/calendar", "/api/analytics/monthly",
                     "/api/analytics/categories", "/api/settings", "/api/notifications",
                     "/api/usage-logs/{log_id}", "/api/subscriptions/{id}/decisions"):
            self.assertIn(path, paths)
        self.assertEqual(set(paths["/api/usage-logs/{log_id}"]), {"patch", "delete"})

    def test_subscription_options(self):
        subscription = self.create_subscription()
        self.assertTrue(subscription["notification_enabled"])
        self.assertEqual(subscription["renewal_reminder_days"], 3)
        self.assertTrue(subscription["include_in_analysis"])
        root = f"/api/subscriptions/{subscription['id']}"
        values = {"notification_enabled": False, "renewal_reminder_days": 0, "include_in_analysis": False}
        changed = self.request("PATCH", root, values)
        for key, value in values.items():
            self.assertEqual(changed[key], value)
        for invalid in [
            {"notification_enabled": None}, {"notification_enabled": "true"},
            {"renewal_reminder_days": -1}, {"renewal_reminder_days": 366},
            {"include_in_analysis": None}, {"include_in_analysis": 1},
        ]:
            self.request("PATCH", root, invalid, 422)
        self.assertEqual(self.request("GET", root), changed)

    def test_usage_create_edit_delete_and_filters(self):
        sid = self.create_subscription()["id"]
        root = f"/api/subscriptions/{sid}/usage-logs"
        self.request("PATCH", "/api/settings", {"auto_tracking_enabled": True})
        self.request("PATCH", f"/api/subscriptions/{sid}", {"android_package": "com.netflix.mediaclient"})
        manual = self.use(sid, 1, memo="TV")
        self.request("POST", "/api/usage-logs/sync", {"entries": [{
            "package_name": "com.netflix.mediaclient",
            "used_date": (today() - timedelta(days=1)).isoformat(), "duration_minutes": 30,
        }]})
        automatic = self.request("GET", root + "?source=mobile_auto")[0]
        notice = self.use(sid, 2, source="notification")
        self.assertEqual(manual["source"], "manual")
        self.assertEqual(manual["used_date"], (today() - timedelta(days=1)).isoformat())
        self.assertEqual(datetime.fromisoformat(manual["created_at"].replace("Z", "+00:00")).astimezone(BUSINESS_TZ).date(), today())
        self.assertEqual(len(self.request("GET", root)), 3)
        self.assertEqual(self.request("GET", root + "?source=mobile_auto"), [automatic])
        day = manual["used_date"]
        self.assertEqual(len(self.request("GET", root + f"?start_date={day}&end_date={day}")), 2)
        changed = self.request("PATCH", f"/api/usage-logs/{automatic['id']}", {
            "used_date": today().isoformat(), "memo": "corrected"
        })
        self.assertEqual(changed["source"], "mobile_auto")
        self.assertEqual(changed["created_at"], automatic["created_at"])
        self.assertGreater(changed["updated_at"], automatic["updated_at"])
        self.request("PATCH", f"/api/usage-logs/{automatic['id']}", {"source": "manual"}, 422)
        self.request("PATCH", f"/api/usage-logs/{automatic['id']}", {"used_date": None}, 422)
        self.request("DELETE", f"/api/usage-logs/{automatic['id']}", expected=204)
        self.request("DELETE", f"/api/usage-logs/{automatic['id']}", expected=404)
        self.assertEqual(self.request("GET", f"/api/subscriptions/{sid}/usage-summary")["total_usage_count"], 2)
        self.request("POST", root, {"used_date": (today() + timedelta(days=1)).isoformat()}, 422)
        self.request("POST", root, {"source": "unknown"}, 422)
        self.request("POST", root, {"source": "mobile_auto"}, 422)  # 자동 기록은 sync로만
        self.request("GET", root + "?source=unknown", expected=422)
        self.request("GET", root + "?start_date=2026-10-01&end_date=2026-09-01", expected=422)
        self.request("PATCH", "/api/usage-logs/999999", {"memo": "x"}, 404)
        self.request("POST", "/api/subscriptions/999999/usage-logs", {}, 404)

    def test_usage_observation_and_cost(self):
        sid = self.create_subscription()["id"]
        path = f"/api/subscriptions/{sid}/usage-summary"
        initial = self.request("GET", path)
        self.assertEqual(initial["observation_days"], 1)
        self.assertEqual(initial["data_status"], "collecting")
        self.assertEqual(initial["usage_count_7d"], 0)
        self.assertIsNone(initial["cost_per_use_30d"])
        self.assertIsNone(initial["previous_30d_usage_count"])
        self.assertIsNone(initial["usage_change_30d"])
        self.age_subscription(sid, 30)
        self.use(sid, 0)
        self.use(sid, 6)
        self.use(sid, 7)
        self.use(sid, 29)
        result = self.request("GET", path)
        self.assertEqual(result["data_status"], "sufficient")
        self.assertEqual((result["usage_count_7d"], result["usage_count_30d"]), (2, 4))
        self.assertIsNone(result["cost_per_use_30d"])  # 실제 결제 근거 없음
        self.assertIsNone(result["previous_30d_usage_count"])
        self.request("POST", "/api/payments", {
            "subscription_id": sid, "amount_won": 12000, "paid_date": today().isoformat()
        }, 201)
        self.assertEqual(self.request("GET", path)["cost_per_use_30d"], 3000)
        self.age_subscription(sid, 60)
        for days in (30, 59, 60, 89, 90):
            self.use(sid, days)
        result = self.request("GET", path)
        self.assertEqual(result["previous_30d_usage_count"], 2)
        self.assertEqual(result["usage_change_30d"], 2)
        self.assertEqual(result["usage_count_90d"], 8)
        self.assertEqual(result["total_usage_count"], 9)
        self.assertEqual(result["observation_days"], 91)  # 소급 기록도 관찰 범위에 포함
        for log in self.request("GET", f"/api/subscriptions/{sid}/usage-logs"):
            self.request("DELETE", f"/api/usage-logs/{log['id']}", expected=204)
        result = self.request("GET", path)
        self.assertEqual(result["total_usage_count"], 0)
        self.assertEqual(result["previous_30d_usage_count"], 0)
        self.assertEqual(result["usage_change_30d"], 0)
        self.assertIsNone(result["cost_per_use_30d"])

    def test_decisions_do_not_change_status(self):
        sid = self.create_subscription()["id"]
        root = f"/api/subscriptions/{sid}"
        for decision in ("keep", "cancel", "hold"):
            record = self.request("POST", root + "/decisions", {"decision": decision, "memo": "test"}, 201)
            self.assertEqual(record["decision"], decision)
            self.assertTrue(record["decided_at"].endswith("Z"))
            self.assertEqual(self.request("GET", root)["status"], "active")
        self.assertEqual(len(self.request("GET", root + "/decisions")), 3)
        self.request("POST", root + "/decisions", {"decision": "paused"}, 422)
        self.request("GET", "/api/subscriptions/999999/decisions", expected=404)
        self.request("POST", "/api/subscriptions/999999/decisions", {"decision": "keep"}, 404)

    def test_calendar_and_analytics(self):
        a = self.create_subscription(price_won=17000, category="OTT", billing_day=31)
        b = self.create_subscription(price_won=5000, category=None)
        for sub, amount in ((a, 17000), (b, 5000)):
            self.request("POST", "/api/payments", {
                "subscription_id": sub["id"], "amount_won": amount, "paid_date": "2026-09-30"
            }, 201)
        self.request("PATCH", f"/api/subscriptions/{a['id']}", {"price_won": 18500, "category": "changed", "status": "canceled"})
        self.assertEqual(self.request("GET", "/api/analytics/monthly?year=2026&month=9")["total_won"], 22000)
        categories = self.request("GET", "/api/analytics/categories?year=2026&month=9")
        self.assertEqual([row["category"] for row in categories], ["OTT", None])
        self.assertAlmostEqual(sum(row["ratio"] for row in categories), 1)
        self.assertEqual(categories[0]["amount_won"], 17000)
        self.request("PATCH", f"/api/subscriptions/{a['id']}", {"include_in_analysis": False})
        self.assertEqual(self.request("GET", "/api/analytics/monthly?year=2026&month=9")["total_won"], 5000)
        paid = [r for r in self.request("GET", "/api/calendar?year=2026&month=9") if r["type"] == "paid"]
        self.assertEqual(len(paid), 2)  # 분석 제외/해지해도 실제 기록 보존
        for path in ("/api/calendar", "/api/analytics/monthly", "/api/analytics/categories"):
            self.request("GET", path + "?year=2026&month=13", expected=422)
            self.request("GET", path + "?year=0&month=9", expected=422)
        self.request("PATCH", f"/api/subscriptions/{b['id']}", {"include_in_analysis": False})
        self.assertEqual(self.request("GET", "/api/analytics/categories?year=2026&month=9"), [])

    def test_settings_and_notification_switches(self):
        current = today()
        sid = self.create_subscription(billing_day=current.day)["id"]
        self.age_subscription(sid, 8)
        notices = self.request("GET", "/api/notifications")
        self.assertEqual({item["type"] for item in notices}, {"renewal"})  # 7일 미사용 알림은 없음
        values = {"notifications_enabled": False, "recommendation_enabled": False}
        self.assertEqual(self.request("PATCH", "/api/settings", values), {
            **values, "auto_tracking_enabled": False, "usage_check_enabled": True, "usage_check_time": "21:00",
        })
        self.assertEqual(self.request("GET", "/api/settings").items() >= values.items(), True)
        self.assertEqual(self.request("GET", "/api/notifications"), [])
        self.request("PATCH", "/api/settings", {"notifications_enabled": True})
        self.assertEqual(len(self.request("GET", "/api/notifications")), 1)
        self.request("PATCH", f"/api/subscriptions/{sid}", {"notification_enabled": False})
        self.assertEqual(self.request("GET", "/api/notifications"), [])
        self.request("PATCH", f"/api/subscriptions/{sid}", {"notification_enabled": True})
        self.use(sid)
        self.assertEqual([r["type"] for r in self.request("GET", "/api/notifications")], ["renewal"])
        self.request("PATCH", "/api/settings", {"notifications_enabled": None}, 422)
        self.request("PATCH", "/api/settings", {"recommendation_enabled": "yes"}, 422)
        self.request("PATCH", "/api/settings", {"hide_service_names": True}, 422)  # 삭제된 설정


class CalculationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="figma-calculations-")
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(URL.create("sqlite", database=str(Path(self.temp.name) / "test.db")))
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, "connect", enable_foreign_keys)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.db.add(AppSettings(id=1))
        self.db.commit()

    def sub(self, **values):
        item = Subscription(name="service", price_won=1000, billing_day=31, billing_cycle="monthly", **values)
        self.db.add(item)
        self.db.commit()
        return item

    def test_month_ends_and_leap_year(self):
        sub = self.sub()
        self.assertEqual(scheduled_date(sub, 2026, 2), date(2026, 2, 28))
        self.assertEqual(scheduled_date(sub, 2028, 2), date(2028, 2, 29))
        self.assertEqual(scheduled_date(sub, 2026, 4), date(2026, 4, 30))
        self.assertEqual(next_renewal(sub, date(2026, 2, 28)), date(2026, 2, 28))
        self.assertEqual(next_renewal(sub, date(2026, 12, 31)), date(2026, 12, 31))
        sub.billing_day = 1
        self.assertEqual(next_renewal(sub, date(2026, 12, 31)), date(2027, 1, 1))
        sub.billing_cycle, sub.billing_month, sub.billing_day = "yearly", 2, 29
        self.assertEqual(next_renewal(sub, date(2026, 2, 28)), date(2026, 2, 28))
        self.assertEqual(next_renewal(sub, date(2027, 3, 1)), date(2028, 2, 29))
        self.assertIsNone(scheduled_date(sub, 2026, 3))

    def test_dashboard_sort_total_and_calendar_dual_items(self):
        first = self.sub()
        first.billing_day = 28
        second = self.sub()
        second.billing_day = 10
        annual = self.sub()
        annual.billing_cycle, annual.billing_month, annual.billing_day = "yearly", 2, 28
        annual.price_won = 12000
        later = self.sub()
        later.billing_cycle, later.billing_month = "yearly", 3
        paused = self.sub(status="paused")
        self.db.add(PaymentRecord(subscription_id=first.id, amount_won=900, paid_date=date(2026, 2, 28)))
        self.db.commit()
        with patch("app.routers.dashboard.today", return_value=date(2026, 2, 28)):
            dashboard = get_dashboard(self.db)
        # 월 환산 합계: 월간 1000 × 2 + 연간 12000/12 + 연간 1000/12(83). 일시정지 제외
        self.assertEqual(dashboard.monthly_total_won, 1000 + 1000 + 1000 + 83)
        self.assertEqual(dashboard.active_subscription_count, 4)
        self.assertEqual([item.id for item in dashboard.subscriptions], [first.id, annual.id, second.id, later.id])
        self.assertEqual([item.d_day for item in dashboard.subscriptions], [0, 0, 10, 31])
        with patch("app.routers.calendar.today", return_value=date(2026, 2, 28)):
            rows = get_calendar(2026, 2, self.db)
        # 이번 달 결제 기록이 있으면 같은 구독의 예정 항목은 숨깁니다.
        self.assertEqual({row.type for row in rows if row.subscription_id == first.id}, {"paid"})
        self.assertEqual({row.type for row in rows if row.subscription_id == annual.id}, {"scheduled"})
        self.assertNotIn(paused.id, [row.subscription_id for row in rows])
        self.assertTrue(all(row.date == date(2026, 2, 28) for row in rows))

    def test_observation_thresholds_and_configurable_status(self):
        sub = self.sub()
        fixed = date(2026, 9, 30)
        for days in (1, 29, 30, 59, 60, 90):
            start = datetime.combine(fixed - timedelta(days=days - 1), time.min, BUSINESS_TZ)
            sub.created_at = start.astimezone(timezone.utc).replace(tzinfo=None)
            self.db.commit()
            with patch("app.routers.usage_logs.today", return_value=fixed):
                result = get_usage_summary(sub.id, self.db)
            self.assertEqual(result.observation_days, days)
            self.assertEqual(result.data_status, "collecting" if days < 30 else "sufficient")
            self.assertEqual(result.previous_30d_usage_count, None if days < 60 else 0)
            self.assertIsNone(result.cost_per_use_30d)
        with patch("app.routers.usage_logs.today", return_value=fixed), patch("app.routers.usage_logs.USAGE_EVALUATION_DAYS", 90):
            sub.created_at = datetime(2026, 9, 1)
            self.db.commit()
            self.assertEqual(get_usage_summary(sub.id, self.db).data_status, "collecting")

    def test_notification_boundaries(self):
        sub = self.sub()
        sub.billing_day = 10
        sub.renewal_reminder_days = 7
        sub.created_at = datetime(2026, 9, 1)
        self.db.add(UsageLog(subscription_id=sub.id, used_date=date(2026, 9, 1)))
        self.db.commit()
        with patch("app.routers.notifications.today", return_value=date(2026, 9, 3)):
            self.assertEqual([n.type for n in notification_candidates(self.db)], ["renewal"])
        with patch("app.routers.notifications.today", return_value=date(2026, 9, 8)):
            self.assertEqual([n.type for n in notification_candidates(self.db)], ["renewal"])
        sub.renewal_reminder_days = 0
        self.db.commit()
        # 결제 알림 기간이 아니어도 결제 5일 전~하루 전이면 해지 권장 기간 알림
        with patch("app.routers.notifications.today", return_value=date(2026, 9, 9)):
            self.assertEqual([n.type for n in notification_candidates(self.db)], ["cancel_window"])
        sub.status = "canceled"
        self.db.commit()
        with patch("app.routers.notifications.today", return_value=date(2026, 9, 10)):
            self.assertEqual(notification_candidates(self.db), [])


class MigrationTests(unittest.TestCase):
    def test_renewal_date_version(self):
        with tempfile.TemporaryDirectory(prefix="migration-renewal-") as temp:
            path = Path(temp) / "old.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript("""
                    CREATE TABLE subscriptions (
                        id INTEGER PRIMARY KEY, name TEXT, price_won INTEGER, billing_cycle TEXT,
                        renewal_date DATE, category TEXT, status TEXT, created_at DATETIME, updated_at DATETIME
                    );
                    INSERT INTO subscriptions VALUES
                        (1, 'annual', 12000, 'yearly', '2028-02-29', NULL, 'active', '2026-09-01', '2026-09-01'),
                        (2, 'monthly', 1000, 'monthly', '2026-10-31', NULL, 'paused', '2026-09-01', '2026-09-01');
                """)
            migrate_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT id,billing_day,billing_month FROM subscriptions ORDER BY id"
                ).fetchall(), [(1, 29, 2), (2, 31, None)])

    def test_prior_schema_preserves_data(self):
        with tempfile.TemporaryDirectory(prefix="migration-test-") as temp:
            path = Path(temp) / "old.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript("""
                    CREATE TABLE subscriptions (
                        id INTEGER PRIMARY KEY, name TEXT NOT NULL, price_won INTEGER NOT NULL,
                        billing_cycle TEXT NOT NULL, billing_day INTEGER NOT NULL, billing_month INTEGER,
                        category TEXT, status TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                    );
                    INSERT INTO subscriptions VALUES (7, 'Netflix', 17000, 'monthly', 31, NULL, 'OTT', 'active',
                        '2026-09-01 10:00:00', '2026-09-01 10:00:00');
                    CREATE TABLE usage_logs (
                        id INTEGER PRIMARY KEY, subscription_id INTEGER REFERENCES subscriptions(id),
                        checked_at DATETIME NOT NULL, memo TEXT
                    );
                    INSERT INTO usage_logs VALUES (9, 7, '2026-09-29 16:30:00', 'TV');
                    CREATE TABLE payment_records (
                        id INTEGER PRIMARY KEY, subscription_id INTEGER REFERENCES subscriptions(id),
                        amount_won INTEGER, paid_date DATE, category_snapshot TEXT, created_at DATETIME
                    );
                    INSERT INTO payment_records VALUES (11, 7, 17000, '2026-09-15', 'OTT', '2026-09-15 00:00:00');
                """)
            with closing(sqlite3.connect(path)) as original:
                before = list(original.iterdump())
            backup = migrate_database(path)
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(backup)) as snapshot:
                self.assertEqual(list(snapshot.iterdump()), before)
            engine = create_engine(URL.create("sqlite", database=str(path)))
            try:
                with Session(engine) as db:
                    sub = db.get(Subscription, 7)
                    self.assertEqual(sub.renewal_reminder_days, 3)
                    self.assertTrue(sub.notification_enabled)
                    log = db.get(UsageLog, 9)
                    self.assertEqual(log.used_date, date(2026, 9, 30))
                    self.assertEqual(log.created_at, datetime(2026, 9, 29, 16, 30))
                    self.assertEqual(log.source, "manual")
                    self.assertEqual(db.get(PaymentRecord, 11).amount_won, 17000)
                    self.assertIsNotNone(db.get(AppSettings, 1))
                async def start():
                    async with main.lifespan(main.app):
                        pass
                with patch.object(main, "engine", engine):
                    asyncio.run(start())
            finally:
                engine.dispose()

    def test_unknown_data_does_not_replace_original(self):
        with tempfile.TemporaryDirectory(prefix="migration-refusal-") as temp:
            path = Path(temp) / "old.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("CREATE TABLE custom_data (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO custom_data VALUES (1)")
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unknown tables"):
                migrate_database(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(path.parent.glob("*.migrating-*.db")))


if __name__ == "__main__":
    unittest.main()
