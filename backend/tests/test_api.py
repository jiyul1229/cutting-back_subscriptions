"""실제 Uvicorn + 임시 SQLite를 사용하는 표준 unittest 통합 테스트."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

from app import main
from app.calculations import today
from app.models import Base, Subscription, UsageLog
from app.routers.usage_logs import get_usage_summary


ROOT = Path(__file__).resolve().parents[1]


class LiveApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="subscription-api-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.db_path = Path(cls.temp.name) / "test.db"
        cls.server_log = open(Path(cls.temp.name) / "server.log", "w+", encoding="utf-8")
        cls.addClassCleanup(cls.server_log.close)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{port}"
        env = {
            **os.environ, "SUBSCRIPTION_DB_PATH": str(cls.db_path),
            "PYTHONDONTWRITEBYTECODE": "1",
            "USAGE_EVALUATION_DAYS": "30",
            "CORS_ALLOW_ORIGINS": "http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006",
        }
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
            cwd=ROOT, env=env, stdout=cls.server_log, stderr=subprocess.STDOUT,
        )
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            if cls.process.poll() is not None:
                break
            try:
                with urlopen(cls.base_url + "/health", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError):
                time.sleep(0.1)
        cls.server_log.seek(0)
        raise RuntimeError("Server startup failed: " + cls.server_log.read())

    @classmethod
    def stop_server(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=5)

    def request(self, method, path, payload=None, expected=200):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(self.base_url + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            content = response.read().decode("utf-8")
            self.assertEqual(response.status, expected, content)
            return json.loads(content) if "application/json" in response.headers.get("Content-Type", "") else content

    def create_subscription(self, auto_payments=False, **changes):
        created = self.request("POST", "/api/subscriptions", {
            "name": "Netflix", "price_won": 17000, "billing_day": 15, "category": "OTT", **changes,
        }, 201)
        if not auto_payments:
            # 결제 기록을 직접 다루는 테스트가 날짜에 따라 흔들리지 않도록 자동 결제 기록을 끕니다.
            with sqlite3.connect(self.db_path) as connection:
                connection.execute("UPDATE subscriptions SET auto_payment_checked_on=? WHERE id=?",
                                   (today().isoformat(), created["id"]))
            connection.close()
        return created


class ApiTests(LiveApiTestCase):
    def test_00_empty_states_and_docs(self):
        self.assertEqual(self.request("GET", "/health"), {"status": "ok"})
        self.assertEqual(self.request("GET", "/api/subscriptions"), [])
        self.assertEqual(self.request("GET", "/api/payments"), [])
        self.assertIn("swagger-ui", self.request("GET", "/docs"))
        paths = self.request("GET", "/openapi.json")["paths"]
        self.assertEqual(set(paths["/api/subscriptions"]), {"post", "get"})
        self.assertEqual(set(paths["/api/subscriptions/{id}"]), {"get", "patch", "delete"})
        self.assertEqual(set(paths["/api/payments"]), {"post", "get"})
        for suffix in ("check-ins", "usage-logs", "usage-summary"):
            self.assertIn("/api/subscriptions/{id}/" + suffix, paths)

    def test_subscription_crud(self):
        created = self.create_subscription(billing_day=31, category="custom category")
        detail = f"/api/subscriptions/{created['id']}"
        self.assertEqual(created["billing_cycle"], "monthly")
        self.assertIsNone(created["billing_month"])
        self.assertEqual(created["status"], "active")
        self.assertNotIn("renewal_date", created)
        self.assertEqual(self.request("GET", detail), created)
        self.assertIn(created, self.request("GET", "/api/subscriptions"))
        changed = self.request("PATCH", detail, {"price_won": 18500, "status": "canceled", "category": None})
        self.assertEqual(changed["price_won"], 18500)
        self.assertEqual(changed["status"], "canceled")
        self.assertIsNone(changed["category"])
        self.assertEqual(changed["billing_day"], 31)
        self.assertEqual(changed["created_at"], created["created_at"])
        self.assertGreater(changed["updated_at"], created["updated_at"])
        self.assertEqual(self.request("PATCH", detail, {}), changed)
        self.assertIn(changed, self.request("GET", "/api/subscriptions"))
        # 삭제는 숨김: 목록에서 빠지고 상세는 조회되며 되살릴 수 있습니다.
        self.request("DELETE", detail, expected=204)
        deleted = self.request("GET", detail)
        self.assertIsNotNone(deleted["deleted_at"])
        self.assertNotIn(created["id"], [s["id"] for s in self.request("GET", "/api/subscriptions")])
        self.assertIn(created["id"], [s["id"] for s in self.request("GET", "/api/subscriptions?include_deleted=true")])
        self.request("PATCH", detail, {"price_won": 1}, 404)
        self.request("DELETE", detail, expected=404)
        restored = self.request("POST", detail + "/restore")
        self.assertIsNone(restored["deleted_at"])
        self.assertEqual(restored["status"], "canceled")
        self.request("POST", detail + "/restore", expected=409)

    def test_schedule_validation_and_patch_merge(self):
        created = self.create_subscription(billing_cycle="yearly", billing_month=2, billing_day=29)
        detail = f"/api/subscriptions/{created['id']}"
        for payload in [
            {"billing_month": None}, {"billing_day": 30},
            {"billing_cycle": "monthly"}, {"billing_month": 4, "billing_day": 31},
        ]:
            with self.subTest(payload=payload):
                self.request("PATCH", detail, payload, 422)
        self.assertEqual(self.request("GET", detail), created)
        monthly = self.request("PATCH", detail, {"billing_cycle": "monthly", "billing_month": None})
        self.assertIsNone(monthly["billing_month"])
        self.request("PATCH", detail, {"billing_cycle": "yearly"}, 422)
        yearly = self.request("PATCH", detail, {"billing_cycle": "yearly", "billing_month": 12})
        self.assertEqual(yearly["billing_month"], 12)
        invalid = [
            {"billing_cycle": "yearly"}, {"billing_month": 2},
            {"billing_cycle": "yearly", "billing_month": 2, "billing_day": 30},
            {"billing_cycle": "yearly", "billing_month": 4, "billing_day": 31},
            {"billing_cycle": "weekly"}, {"billing_day": 0}, {"billing_day": 32},
            {"billing_month": 13}, {"billing_day": True},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.request("POST", "/api/subscriptions",
                             {"name": "test", "price_won": 100, "billing_day": 15, **changes}, 422)

    def test_invalid_inputs_and_missing_ids(self):
        created = self.create_subscription()
        detail = f"/api/subscriptions/{created['id']}"
        for field, value in [
            ("price_won", 0), ("price_won", -1), ("price_won", 1.5),
            ("price_won", True), ("price_won", "100"), ("price_won", 2**63),
            ("status", "deleted"), ("name", "  "), ("name", None),
            ("billing_day", None), ("renewal_date", "2026-09-15"), ("unknown", 1),
        ]:
            with self.subTest(field=field, value=value):
                self.request("POST", "/api/subscriptions",
                             {"name": "test", "price_won": 100, "billing_day": 15, field: value}, 422)
                self.request("PATCH", detail, {field: value}, 422)
        for method, suffix, payload in [
            ("GET", "", None), ("PATCH", "", {"status": "paused"}),
            ("POST", "/check-ins", {}), ("GET", "/usage-logs", None),
            ("GET", "/usage-summary", None),
        ]:
            self.request(method, "/api/subscriptions/999999" + suffix, payload, 404)
        self.request("GET", "/api/subscriptions/0", expected=422)
        self.request("GET", f"/api/subscriptions/{2**63}", expected=422)
        self.request("POST", "/api/payments",
                     {"subscription_id": 999999, "amount_won": 100, "paid_date": "2026-09-01"}, 404)
        self.request("GET", "/api/payments?subscription_id=999999", expected=404)
        self.assertEqual(self.request("GET", detail), created)

    def test_check_ins_logs_and_summary(self):
        created = self.create_subscription()
        root = f"/api/subscriptions/{created['id']}"
        self.assertEqual(self.request("GET", root + "/usage-logs"), [])
        empty = self.request("GET", root + "/usage-summary")
        self.assertEqual((empty["usage_count_30d"], empty["usage_count_90d"]), (0, 0))
        now = datetime.now(timezone.utc)
        for days in (1, 29, 31, 89, 91):
            self.request("POST", root + "/check-ins",
                         {"checked_at": (now - timedelta(days=days)).isoformat(), "memo": str(days)}, 201)
        # 다른 구독의 이용 기록은 집계하지 않습니다.
        other = self.create_subscription()
        self.request("POST", f"/api/subscriptions/{other['id']}/check-ins", {}, 201)
        summary = self.request("GET", root + "/usage-summary")
        self.assertEqual(summary["usage_count_30d"], 2)
        self.assertEqual(summary["usage_count_90d"], 4)
        logs = self.request("GET", root + "/usage-logs")
        self.assertEqual([log["memo"] for log in logs], ["1", "29", "31", "89", "91"])
        tz_log = self.request("POST", root + "/check-ins",
                              {"checked_at": "2020-01-01T12:00:00+09:00"}, 201)
        self.assertEqual(tz_log["used_date"], "2020-01-01")
        self.assertTrue(tz_log["created_at"].endswith("Z"))
        self.request("POST", root + "/check-ins",
                     {"checked_at": (now + timedelta(days=1)).isoformat()}, 422)
        self.request("POST", root + "/check-ins", {"subscription_id": other["id"]}, 422)
        self.request("POST", root + "/check-ins", {"checked_at": None}, 422)
        self.request("POST", root + "/check-ins", {"checked_at": "bad date"}, 422)
        self.request("POST", root + "/check-ins", {}, 201)
        self.assertEqual(self.request("GET", root + "/usage-summary")["usage_count_30d"], 3)

    def test_payments_preserve_history_and_filter(self):
        created = self.create_subscription()
        sid = created["id"]
        first = self.request("POST", "/api/payments",
                             {"subscription_id": sid, "amount_won": 17000, "paid_date": "2026-09-15"}, 201)
        self.request("PATCH", f"/api/subscriptions/{sid}",
                     {"price_won": 18500, "category": "new category", "status": "paused"})
        second = self.request("POST", "/api/payments",
                              {"subscription_id": sid, "amount_won": 18500, "paid_date": "2026-10-15"}, 201)
        rows = self.request("GET", f"/api/payments?subscription_id={sid}")
        self.assertEqual(rows, [second, first])
        self.assertEqual(first["amount_won"], 17000)
        self.assertEqual(first["category_snapshot"], "OTT")
        self.assertEqual(second["category_snapshot"], "new category")
        filtered = self.request("GET", f"/api/payments?subscription_id={sid}&start_date=2026-09-15&end_date=2026-09-15")
        self.assertEqual(filtered, [first])
        for changes in [{"amount_won": 0}, {"amount_won": 1.5}, {"amount_won": True},
                        {"amount_won": 2**63}, {"subscription_id": 0},
                        {"paid_date": "2026-02-30"}, {"status": "pending"}]:
            self.request("POST", "/api/payments",
                         {"subscription_id": sid, "amount_won": 100, "paid_date": "2026-09-01", **changes}, 422)
        self.request("GET", "/api/payments?start_date=2026-10-01&end_date=2026-09-01", expected=422)

    def test_cors(self):
        def raw_request(method, origin=None, **headers):
            if origin is not None:
                headers["Origin"] = origin
            req = Request(self.base_url + "/health", method=method, headers=headers)
            try:
                return urlopen(req, timeout=5)
            except HTTPError as exc:
                return exc

        for origin in ("http://localhost:8081", "http://127.0.0.1:8081", "http://localhost:19006"):
            for method in ("GET", "POST", "PATCH", "DELETE"):
                with raw_request("OPTIONS", origin, **{
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "content-type",
                }) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
                    self.assertIsNone(response.headers.get("Access-Control-Allow-Credentials"))
            with raw_request("GET", origin) as response:
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
        for origin, method, header in (
            ("http://untrusted.example", "GET", "content-type"),
            ("http://localhost:8081", "PUT", "content-type"),
            ("http://localhost:8081", "POST", "x-unapproved-header"),
        ):
            with raw_request("OPTIONS", origin, **{
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": header,
            }) as response:
                self.assertEqual(response.status, 400)
        # CORS는 인증이 아닙니다. Origin 없는 네이티브 요청도 정상 처리합니다.
        with raw_request("GET") as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
        with raw_request("GET", "http://untrusted.example") as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_response_contract(self):
        subscription = self.create_subscription(category=None)
        sid = subscription["id"]
        log = self.request("POST", f"/api/subscriptions/{sid}/check-ins", {}, 201)
        payment = self.request("POST", "/api/payments", {
            "subscription_id": sid, "amount_won": 100, "paid_date": "2026-09-30",
        }, 201)
        for value in (subscription["created_at"], subscription["updated_at"],
                      log["created_at"], log["updated_at"], payment["created_at"]):
            self.assertTrue(value.endswith("Z"))
            self.assertEqual(datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset(), timedelta(0))
        self.assertEqual(payment["paid_date"], "2026-09-30")
        self.assertIsNone(subscription["category"])
        self.assertIsNone(subscription["billing_month"])
        self.assertIsNone(log["memo"])
        self.assertIsNone(payment["category_snapshot"])
        missing = self.request("GET", "/api/subscriptions/999999", expected=404)
        self.assertEqual(missing, {"detail": "Subscription not found"})
        for error in (
            self.request("POST", "/api/subscriptions", {}, 422),
            self.request("PATCH", f"/api/subscriptions/{sid}", {"billing_cycle": "yearly"}, 422),
            self.request("GET", "/api/payments?start_date=2026-10-01&end_date=2026-09-01", expected=422),
        ):
            self.assertIsInstance(error["detail"], list)
            self.assertTrue(error["detail"])
            self.assertTrue({"loc", "msg", "type"} <= error["detail"][0].keys())
        spec = self.request("GET", "/openapi.json")["components"]["schemas"]
        self.assertEqual(spec["SubscriptionResponse"]["properties"]["created_at"]["format"], "date-time")
        self.assertEqual(spec["PaymentRecordResponse"]["properties"]["paid_date"]["format"], "date")

    def test_database_constraints(self):
        subscription = self.create_subscription()
        connection = sqlite3.connect(self.db_path)
        self.addCleanup(connection.close)
        connection.execute("PRAGMA foreign_keys=ON")
        for sql, values in [
            ("INSERT INTO usage_logs (subscription_id, used_date, source, created_at, updated_at) VALUES (?, ?, 'manual', '2026-09-01', '2026-09-01')", (999999, "2026-09-01")),
            ("UPDATE subscriptions SET price_won = 0 WHERE id = ?", (subscription["id"],)),
            ("UPDATE subscriptions SET billing_day = 0 WHERE id = ?", (subscription["id"],)),
            ("UPDATE subscriptions SET billing_cycle = 'yearly', billing_month = NULL WHERE id = ?", (subscription["id"],)),
            ("UPDATE subscriptions SET billing_cycle = 'yearly', billing_month = 2, billing_day = 30 WHERE id = ?", (subscription["id"],)),
            ("INSERT INTO payment_records (subscription_id, amount_won, paid_date, created_at) VALUES (?, 0, '2026-09-01', '2026-09-01')", (subscription["id"],)),
        ]:
            with self.subTest(sql=sql):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql, values)
                connection.rollback()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"subscriptions", "usage_logs", "payment_records", "decision_history", "app_settings"})
        columns = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(payment_records)")}
        self.assertEqual(columns["amount_won"], "INTEGER")
        self.assertEqual(columns["paid_date"], "DATE")


class BoundaryTests(unittest.TestCase):
    def test_cors_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main.read_cors_origins(), ["http://localhost:8081", "http://127.0.0.1:8081"])
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": ""}):
            self.assertEqual(main.read_cors_origins(), [])
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": " http://192.168.0.10:8081 , http://localhost:19006 "}):
            self.assertEqual(main.read_cors_origins(), ["http://192.168.0.10:8081", "http://localhost:19006"])
        for origin in ("*", "http://*.example.com", "exp://localhost:8081", "http://localhost:8081/path"):
            with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": origin}):
                with self.assertRaises(ValueError):
                    main.read_cors_origins()

    def test_exact_usage_windows(self):
        with tempfile.TemporaryDirectory(prefix="usage-boundary-") as temp:
            engine = create_engine(URL.create("sqlite", database=str(Path(temp) / "test.db")))
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as db:
                    subscription = Subscription(name="test", price_won=100, billing_cycle="monthly", billing_day=1)
                    db.add(subscription)
                    db.flush()
                    fixed = datetime(2026, 9, 30).date()
                    dates = [fixed, fixed - timedelta(days=29),
                             fixed - timedelta(days=30),
                             fixed - timedelta(days=89),
                             fixed - timedelta(days=90),
                             fixed + timedelta(days=1)]
                    db.add_all([UsageLog(subscription_id=subscription.id, used_date=value) for value in dates])
                    db.commit()
                    with patch("app.routers.usage_logs.today", return_value=fixed):
                        result = get_usage_summary(subscription.id, db)
                    self.assertEqual(result.usage_count_30d, 2)
                    self.assertEqual(result.usage_count_90d, 4)
                    self.assertEqual(len(subscription.usage_logs), 6)
            finally:
                engine.dispose()

    def test_legacy_database_is_not_changed(self):
        with tempfile.TemporaryDirectory(prefix="legacy-schema-") as temp:
            engine = create_engine(URL.create("sqlite", database=str(Path(temp) / "legacy.db")))
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, renewal_date DATE)")
                connection.exec_driver_sql("INSERT INTO subscriptions VALUES (1, '2026-09-15')")

            async def start():
                async with main.lifespan(main.app):
                    self.fail("Legacy database should require migration")

            try:
                with patch.object(main, "engine", engine):
                    with self.assertRaisesRegex(RuntimeError, "Legacy subscription schema"):
                        asyncio.run(start())
                with engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("SELECT * FROM subscriptions").all(),
                                     [(1, "2026-09-15")])
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
