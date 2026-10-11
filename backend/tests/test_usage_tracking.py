"""이용 시간 자동 측정·수기 기록·이용 확인 알림·자동 결제 기록 검증."""
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session

from app.auto_payments import ensure_auto_payments
from app.calculations import today
from app.database import enable_foreign_keys
from app.models import Base, PaymentRecord, Subscription
from test_api import LiveApiTestCase

NETFLIX = "com.netflix.mediaclient"


class UsageTrackingApiTests(LiveApiTestCase):
    def setUp(self):
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            for table in ("decision_history", "usage_logs", "payment_records", "subscriptions"):
                connection.execute(f"DELETE FROM {table}")
            connection.execute(
                "UPDATE app_settings SET notifications_enabled=1, auto_tracking_enabled=1, "
                "usage_check_enabled=1, usage_check_time='21:00'"
            )

    def day(self, days_ago=0):
        return (today() - timedelta(days=days_ago)).isoformat()

    def sync(self, *entries, expected=200):
        return self.request("POST", "/api/usage-logs/sync", {"entries": [
            {"package_name": package, "used_date": self.day(days_ago), "duration_minutes": minutes}
            for package, days_ago, minutes in entries
        ]}, expected)

    def test_android_package_link(self):
        created = self.create_subscription(android_package=" com.netflix.mediaclient ")
        self.assertEqual(created["android_package"], NETFLIX)
        self.request("POST", "/api/subscriptions", {
            "name": "Copy", "price_won": 1000, "billing_day": 1, "android_package": NETFLIX,
        }, 409)
        other = self.create_subscription(name="YouTube")
        self.request("PATCH", f"/api/subscriptions/{other['id']}", {"android_package": NETFLIX}, 409)
        for bad in ("netflix", "com..netflix", "1com.netflix", "com.net flix"):
            self.request("PATCH", f"/api/subscriptions/{other['id']}", {"android_package": bad}, 422)
        # null로 연결을 해제하면 다른 구독에 연결할 수 있습니다.
        self.request("PATCH", f"/api/subscriptions/{created['id']}", {"android_package": None})
        linked = self.request("PATCH", f"/api/subscriptions/{other['id']}", {"android_package": NETFLIX})
        self.assertEqual(linked["android_package"], NETFLIX)

    def test_sync_upserts_one_auto_log_per_day(self):
        sid = self.create_subscription(android_package=NETFLIX)["id"]
        logs = f"/api/subscriptions/{sid}/usage-logs"
        self.assertEqual(self.sync((NETFLIX, 0, 40), (NETFLIX, 1, 90), ("com.unknown.app", 0, 10)), {
            "created": 2, "updated": 0, "deleted": 0, "unmatched_packages": ["com.unknown.app"],
        })
        # 같은 날을 다시 보내면 새로 쌓지 않고 덮어씁니다.
        self.assertEqual(self.sync((NETFLIX, 0, 40), (NETFLIX, 1, 95))["updated"], 1)
        auto = self.request("GET", logs + "?source=mobile_auto")
        self.assertEqual([(log["duration_minutes"], log["device"]) for log in auto], [(40, "phone"), (95, "phone")])
        # 수기 기록은 동기화와 별개로 남습니다.
        self.request("POST", logs, {"used_date": self.day(0), "device": "tv", "duration_minutes": 120}, 201)
        self.assertEqual(self.sync((NETFLIX, 0, 0))["deleted"], 1)
        remaining = self.request("GET", logs)
        self.assertEqual([(log["source"], log["device"]) for log in remaining],
                         [("manual", "tv"), ("mobile_auto", "phone")])
        summary = self.request("GET", f"/api/subscriptions/{sid}/usage-summary")
        self.assertEqual((summary["usage_minutes_7d"], summary["usage_minutes_30d"]), (215, 215))
        self.assertEqual(summary["total_usage_count"], 2)

    def test_sync_validation_and_setting(self):
        self.create_subscription(android_package=NETFLIX)
        self.sync((NETFLIX, -1, 10), expected=422)  # 미래 날짜
        self.sync((NETFLIX, 0, 1441), expected=422)
        self.sync((NETFLIX, 0, 10), (NETFLIX, 0, 20), expected=422)  # 같은 날 중복
        self.request("PATCH", "/api/settings", {"auto_tracking_enabled": False})
        self.sync((NETFLIX, 0, 10), expected=409)

    def test_manual_log_fields(self):
        sid = self.create_subscription()["id"]
        root = f"/api/subscriptions/{sid}/usage-logs"
        log = self.request("POST", root, {"device": "tablet", "duration_minutes": 50, "memo": "침대에서"}, 201)
        self.assertEqual((log["device"], log["duration_minutes"], log["used_date"]), ("tablet", 50, self.day(0)))
        plain = self.request("POST", root, {}, 201)
        self.assertIsNone(plain["duration_minutes"])
        self.assertIsNone(plain["device"])
        for bad in ({"device": "watch"}, {"duration_minutes": 0}, {"duration_minutes": "30"}):
            self.request("POST", root, bad, 422)
        changed = self.request("PATCH", f"/api/usage-logs/{log['id']}", {"device": "tv", "duration_minutes": None})
        self.assertEqual((changed["device"], changed["duration_minutes"]), ("tv", None))

    def test_usage_checks(self):
        tracked = self.create_subscription(android_package=NETFLIX)["id"]
        manual_only = self.create_subscription(name="Watcha")["id"]
        paused = self.create_subscription(name="Paused", status="paused")["id"]
        self.sync((NETFLIX, 0, 25))
        checks = self.request("GET", "/api/usage-checks")
        self.assertEqual((checks["enabled"], checks["check_time"], checks["date"]), (True, "21:00", self.day(0)))
        self.assertEqual([(i["subscription_id"], i["auto_tracked"], i["today_auto_minutes"]) for i in checks["items"]],
                         [(tracked, True, 25), (manual_only, False, None)])
        self.assertNotIn(paused, [i["subscription_id"] for i in checks["items"]])
        # 알림에서 "봤어요"를 누르면 notification 출처로 기록하고 목록에서 빠집니다.
        self.request("POST", f"/api/subscriptions/{manual_only}/usage-logs",
                     {"source": "notification", "device": "tv"}, 201)
        self.assertEqual([i["subscription_id"] for i in self.request("GET", "/api/usage-checks")["items"]], [tracked])
        self.request("PATCH", "/api/settings", {"usage_check_time": "22:30"})
        self.request("PATCH", "/api/settings", {"usage_check_enabled": False})
        off = self.request("GET", "/api/usage-checks")
        self.assertEqual((off["enabled"], off["check_time"], off["items"]), (False, "22:30", []))
        for bad in ("24:00", "9:00", "21:60", None):
            self.request("PATCH", "/api/settings", {"usage_check_time": bad}, 422)

    def test_auto_payment_on_billing_day(self):
        sid = self.create_subscription(auto_payments=True, billing_day=today().day, price_won=13500)["id"]
        payments = self.request("GET", f"/api/payments?subscription_id={sid}")
        self.assertEqual([(p["amount_won"], p["paid_date"], p["source"]) for p in payments],
                         [(13500, self.day(0), "auto")])
        current = today()
        calendar = self.request("GET", f"/api/calendar?year={current.year}&month={current.month}")
        self.assertEqual([row["type"] for row in calendar if row["subscription_id"] == sid], ["paid"])
        self.assertEqual(self.request(
            "GET", f"/api/analytics/monthly?year={current.year}&month={current.month}")["total_won"], 13500)
        # 실제 청구액으로 고치고, 지워도 다시 생기지 않습니다.
        fixed = self.request("PATCH", f"/api/payments/{payments[0]['id']}", {"amount_won": 12900})
        self.assertEqual((fixed["amount_won"], fixed["source"]), (12900, "auto"))
        self.request("PATCH", f"/api/payments/{payments[0]['id']}", {"amount_won": None}, 422)
        self.request("DELETE", f"/api/payments/{payments[0]['id']}", expected=204)
        self.request("DELETE", f"/api/payments/{payments[0]['id']}", expected=404)
        self.assertEqual(self.request("GET", f"/api/payments?subscription_id={sid}"), [])


class AutoPaymentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="auto-payments-")
        self.addCleanup(temp.cleanup)
        self.engine = create_engine(URL.create("sqlite", database=str(Path(temp.name) / "test.db")))
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, "connect", enable_foreign_keys)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def run_on(self, day):
        with patch("app.auto_payments.today", return_value=day):
            ensure_auto_payments(self.db)
        return [p.paid_date for p in self.db.scalars(select(PaymentRecord).order_by(PaymentRecord.paid_date))]

    def sub(self, **values):
        item = Subscription(**{"name": "s", "price_won": 1000, "billing_cycle": "monthly", "billing_day": 31,
                               "created_at": datetime(2026, 6, 10), **values})
        self.db.add(item)
        self.db.commit()
        return item

    def test_monthly_backfill_from_registration_without_duplicates(self):
        sub = self.sub()
        updated = sub.updated_at
        self.assertEqual(self.run_on(date(2026, 9, 30)), [date(2026, 6, 30), date(2026, 7, 31),
                                                         date(2026, 8, 31), date(2026, 9, 30)])
        self.assertEqual(self.run_on(date(2026, 9, 30)), self.run_on(date(2026, 10, 3)))
        self.db.refresh(sub)
        self.assertEqual(sub.updated_at, updated)  # 자동 처리는 구독 수정 시각을 바꾸지 않음
        self.assertEqual(sub.auto_payment_checked_on, date(2026, 10, 3))

    def test_deleted_paused_and_manual_payments_are_respected(self):
        sub = self.sub()
        self.run_on(date(2026, 7, 1))
        self.db.delete(self.db.scalar(select(PaymentRecord)))
        self.db.commit()
        self.assertEqual(self.run_on(date(2026, 7, 2)), [])  # 지운 기록은 재생성 안 함
        sub.status = "paused"
        self.db.commit()
        self.assertEqual(self.run_on(date(2026, 8, 31)), [])
        sub.status = "active"
        self.db.add(PaymentRecord(subscription_id=sub.id, amount_won=990, paid_date=date(2026, 9, 29)))
        self.db.commit()
        # 일시정지 기간(8월)은 소급하지 않고, 9월은 수기 결제가 있어 건너뜀
        self.assertEqual(self.run_on(date(2026, 10, 31)), [date(2026, 9, 29), date(2026, 10, 31)])

    def test_yearly(self):
        self.sub(billing_cycle="yearly", billing_month=2, billing_day=29, created_at=datetime(2025, 1, 1))
        self.assertEqual(self.run_on(date(2028, 3, 1)), [date(2025, 2, 28), date(2026, 2, 28),
                                                        date(2027, 2, 28), date(2028, 2, 29)])

    def test_registered_on_billing_day_counts_today(self):
        self.sub(billing_day=10, created_at=datetime(2026, 9, 10, 3))
        self.assertEqual(self.run_on(date(2026, 9, 10)), [date(2026, 9, 10)])


if __name__ == "__main__":
    unittest.main()
