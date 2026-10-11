"""명시적으로 실행하는 단일 사용자 개발 DB 마이그레이션.

서버를 중지한 뒤 python -m app.migrate [--database PATH]로 실행합니다.
원본 스냅샷 백업과 새 DB 검증이 끝나기 전에는 원본을 교체하지 않습니다.
"""
import argparse
from contextlib import closing
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sqlite3
import uuid

from sqlalchemy import Boolean, Date, DateTime, URL, create_engine, event, insert
from sqlalchemy.orm import Session

from app.calculations import business_date
from app.database import DATABASE_PATH, enable_foreign_keys
from app.models import AppSettings, Base


def parse_time(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def migrate_database(path: Path) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Database must already exist. Start a new database normally instead.")
    # 동시 실행/잔여 journal이 있는 파일은 교체하지 않습니다.
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise ValueError("Stop all DB users and checkpoint/close SQLite before migration.")
    original_stat = (path.stat().st_mtime_ns, path.stat().st_size)
    token = uuid.uuid4().hex
    backup = path.with_name(path.stem + ".backup-" + token + ".db")
    temporary = path.with_name(path.stem + ".migrating-" + token + ".db")
    with closing(sqlite3.connect(path)) as original, closing(sqlite3.connect(backup)) as snapshot:
        original.backup(snapshot)
    source = sqlite3.connect(backup)
    source.row_factory = sqlite3.Row
    target = create_engine(URL.create("sqlite", database=str(temporary)))
    event.listen(target, "connect", enable_foreign_keys)
    try:
        table_names = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if table_names - set(Base.metadata.tables):
            raise ValueError("Unknown tables found; refusing to discard data.")
        extras = source.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('view','trigger')"
        ).fetchall()
        if extras:
            raise ValueError("Custom views/triggers need a separate migration.")
        Base.metadata.create_all(target)
        with target.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in table_names:
                    continue
                columns = {row[1] for row in source.execute(f'PRAGMA table_info("{table.name}")')}
                # 이전 버전에만 있던 컬럼. 아래에서 새 컬럼으로 변환하거나 버립니다.
                legacy_columns = {
                    "subscriptions": {"renewal_date"},
                    "usage_logs": {"checked_at"},
                    "app_settings": {"hide_service_names"},
                }.get(table.name, set())
                if columns - set(table.columns.keys()) - legacy_columns:
                    raise ValueError(f"Unknown columns in {table.name}; refusing to discard data.")
                for raw in source.execute(f'SELECT * FROM "{table.name}"'):
                    row = dict(raw)
                    row.pop("hide_service_names", None)  # 디자인에 없어 삭제한 설정
                    if table.name == "decision_history" and row.get("decision") == "postpone":
                        row["decision"] = "hold"  # 앱과 이름을 맞춤
                    if table.name == "subscriptions" and "renewal_date" in row:
                        renewal = date.fromisoformat(row.pop("renewal_date"))
                        row.setdefault("billing_day", renewal.day)
                        row.setdefault("billing_month", renewal.month if row["billing_cycle"] == "yearly" else None)
                    if table.name == "usage_logs" and "checked_at" in row:
                        checked = parse_time(row.pop("checked_at"))
                        row.setdefault("used_date", business_date(checked))
                        row.setdefault("source", "manual")
                        row.setdefault("created_at", checked)
                        row.setdefault("updated_at", checked)
                    for column in table.columns:
                        value = row.get(column.name)
                        if value is None:
                            continue
                        if isinstance(column.type, DateTime):
                            row[column.name] = parse_time(value)
                        elif isinstance(column.type, Date) and isinstance(value, str):
                            row[column.name] = date.fromisoformat(value)
                        elif isinstance(column.type, Boolean):
                            if value not in (0, 1):
                                raise ValueError("Invalid boolean value in source DB.")
                            row[column.name] = bool(value)
                    connection.execute(insert(table).values(**row))
            if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
                raise ValueError("Foreign key validation failed.")
            if connection.exec_driver_sql("PRAGMA integrity_check").scalar() != "ok":
                raise ValueError("Integrity validation failed.")
        with Session(target) as session:
            if session.get(AppSettings, 1) is None:
                session.add(AppSettings(id=1))
                session.commit()
        # 보존 대상 행 수까지 검증합니다.
        with target.connect() as connection:
            for name in table_names:
                expected = source.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                actual = connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar()
                if name == "app_settings" and expected == 0:
                    expected = 1
                if actual != expected:
                    raise ValueError(f"Row count mismatch in {name}")
        source.close()
        target.dispose()
        if (path.stat().st_mtime_ns, path.stat().st_size) != original_stat:
            raise RuntimeError("Source DB changed during migration; original was not replaced.")
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise RuntimeError("Source DB reopened during migration; original was not replaced.")
        os.replace(temporary, path)
        return backup
    finally:
        source.close()
        target.dispose()
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args()
    backup = migrate_database(args.database)
    print(f"Migration complete. Original backup: {backup}")
