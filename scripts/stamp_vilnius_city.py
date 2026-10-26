"""One-off backfill of historical refinements to the Vilnius city id.

Dry-run by default. Use ``--apply --expected-count N`` to make the update.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from pino_core.cities import resolve_city
from pino_core.config import load_config, PinoConfig
from pino_core.db import require_current_schema
from pino_core.storage import DatabaseStore, records_table, refinements_table

TARGET_CITY_ID = "lt/vilnius"


class StampCountError(RuntimeError):
    """Raised when the eligible row count does not match the expected count."""


def aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--before must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Config file to load.")
    parser.add_argument(
        "--before",
        required=True,
        type=aware_datetime,
        help="Aware ISO cutoff converted to UTC.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply the update.")
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="Required with --apply; eligible rows expected to be stamped.",
    )
    args = parser.parse_args(argv)
    if args.expected_count is not None and args.expected_count < 0:
        parser.error("--expected-count must be nonnegative")
    if args.apply and args.expected_count is None:
        parser.error("--apply requires --expected-count")
    return args


def eligible_filter(cutoff: datetime) -> ColumnElement[bool]:
    return and_(
        refinements_table.c.content_kind == "event",
        refinements_table.c.city_id.is_(None),
        refinements_table.c.refined_at <= cutoff,
    )


def count_eligible(session: Session, cutoff: datetime) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(refinements_table).where(eligible_filter(cutoff))
        ).scalar_one()
    )


def counts_by_source(session: Session, cutoff: datetime) -> list[tuple[str, int]]:
    rows = session.execute(
        select(records_table.c.source, func.count())
        .select_from(
            refinements_table.join(
                records_table,
                refinements_table.c.record_id == records_table.c.id,
            )
        )
        .where(eligible_filter(cutoff))
        .group_by(records_table.c.source)
        .order_by(records_table.c.source)
    )
    return [(str(source), int(count)) for source, count in rows]


def apply_stamp(session: Session, cutoff: datetime, expected_count: int) -> int:
    actual = count_eligible(session, cutoff)
    if actual != expected_count:
        raise StampCountError(
            f"eligible count mismatch: expected {expected_count}, found {actual}"
        )
    result = session.execute(
        update(refinements_table)
        .where(eligible_filter(cutoff))
        .values(city_id=TARGET_CITY_ID)
    )
    if result.rowcount != expected_count:
        raise StampCountError(
            f"updated row count mismatch: expected {expected_count}, updated {result.rowcount}"
        )
    return result.rowcount


def run_preview(store: DatabaseStore, cutoff: datetime) -> None:
    with Session(store.engine) as session:
        count = count_eligible(session, cutoff)
        sources = counts_by_source(session, cutoff)
    print(f"cutoff: {cutoff.isoformat()}")
    print(f"eligible refinements: {count}")
    for source, source_count in sources:
        print(f"  {source}: {source_count}")
    print("dry run: no updates applied")


def run_apply(store: DatabaseStore, cutoff: datetime, expected_count: int) -> None:
    with Session(store.engine) as session:
        with session.begin():
            count = count_eligible(session, cutoff)
            sources = counts_by_source(session, cutoff)
            stamped = apply_stamp(session, cutoff, expected_count)
    print(f"cutoff: {cutoff.isoformat()}")
    print(f"eligible refinements: {count}")
    for source, source_count in sources:
        print(f"  {source}: {source_count}")
    print(f"stamped refinements: {stamped}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if resolve_city(TARGET_CITY_ID) is None:
        raise RuntimeError(f"target city is not in the registry: {TARGET_CITY_ID}")
    config: PinoConfig = load_config(args.config)
    store = DatabaseStore(config.storage.database_url())
    try:
        require_current_schema(store.engine)
        if args.apply:
            run_apply(store, args.before, args.expected_count)
        else:
            run_preview(store, args.before)
    finally:
        store.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
