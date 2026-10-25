from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pino_core.models import Record, Refinement
from pino_core.storage import SQLiteStore

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location(
    "stamp_vilnius_city",
    SCRIPTS / "stamp_vilnius_city.py",
)
assert spec is not None and spec.loader is not None
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)

CUTOFF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_preview_reports_cutoff_and_count_without_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    record_id = _add_refinement(
        store,
        title="Eligible",
        refined_at=CUTOFF - timedelta(hours=1),
    )

    result = stamp.main(_args(tmp_path, before="2026-06-01T00:00:00Z"))

    output = capsys.readouterr().out
    assert result == 0
    assert "cutoff: 2026-06-01T00:00:00+00:00" in output
    assert "eligible refinements: 1" in output
    assert "dry run: no updates applied" in output
    assert store.list_refinements(record_id)[0].city_id is None


def test_apply_stamps_only_eligible_rows_and_preserves_other_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    eligible_id = _add_refinement(
        store,
        title="Eligible",
        source="alpha",
        refined_at=CUTOFF - timedelta(hours=1),
        location="Old venue",
        schedule={
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [{"start": "2026-06-10T19:00", "end": "2026-06-10T21:00"}],
        },
    )
    stamped_id = _add_refinement(
        store,
        title="Already stamped",
        source="beta",
        city_id=stamp.TARGET_CITY_ID,
        refined_at=CUTOFF - timedelta(hours=1),
    )
    other_city_id = _add_refinement(
        store,
        title="Other city",
        source="beta",
        city_id="fixture/other",
        refined_at=CUTOFF - timedelta(hours=1),
    )
    non_event_id = _add_refinement(
        store,
        title="Advertisement",
        source="beta",
        content_kind="advertisement",
        refined_at=CUTOFF - timedelta(hours=1),
    )
    newer_id = _add_refinement(
        store,
        title="Newer",
        source="beta",
        refined_at=CUTOFF + timedelta(seconds=1),
    )
    before = {
        record_id: store.list_refinements(record_id)[0]
        for record_id in (eligible_id, stamped_id, other_city_id, non_event_id, newer_id)
    }

    result = stamp.main(
        _args(
            tmp_path,
            before="2026-06-01T00:00:00Z",
            apply=True,
            expected_count=1,
        )
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "eligible refinements: 1" in output
    assert "stamped refinements: 1" in output
    eligible = store.list_refinements(eligible_id)[0]
    assert eligible.city_id == stamp.TARGET_CITY_ID
    assert eligible.model_dump(exclude={"city_id"}) == before[eligible_id].model_dump(
        exclude={"city_id"}
    )
    for record_id in (stamped_id, other_city_id, non_event_id, newer_id):
        assert store.list_refinements(record_id)[0] == before[record_id]

    second = stamp.main(
        _args(
            tmp_path,
            before="2026-06-01T00:00:00Z",
            apply=True,
            expected_count=0,
        )
    )
    second_output = capsys.readouterr().out
    assert second == 0
    assert "eligible refinements: 0" in second_output
    assert "stamped refinements: 0" in second_output
    assert store.list_refinements(eligible_id)[0].city_id == stamp.TARGET_CITY_ID


def test_expected_count_mismatch_raises_without_updates(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    record_id = _add_refinement(
        store,
        title="Eligible",
        refined_at=CUTOFF - timedelta(hours=1),
    )

    with pytest.raises(stamp.StampCountError, match="expected 2, found 1"):
        stamp.main(
            _args(
                tmp_path,
                before="2026-06-01T00:00:00Z",
                apply=True,
                expected_count=2,
            )
        )

    assert store.list_refinements(record_id)[0].city_id is None


def test_offset_equivalent_cutoffs_select_the_same_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    _add_refinement(
        store,
        title="At cutoff",
        refined_at=datetime(2026, 5, 31, 21, 0, tzinfo=timezone.utc),
    )
    _add_refinement(
        store,
        title="After cutoff",
        refined_at=datetime(2026, 5, 31, 21, 0, 1, tzinfo=timezone.utc),
    )

    stamp.main(_args(tmp_path, before="2026-06-01T00:00:00+03:00"))
    offset_output = capsys.readouterr().out
    stamp.main(_args(tmp_path, before="2026-05-31T21:00:00Z"))
    utc_output = capsys.readouterr().out

    assert offset_output == utc_output
    assert "eligible refinements: 1" in offset_output


@pytest.mark.parametrize(
    "extra",
    [
        {"before": "2026-06-01T00:00:00"},
        {"before": "2026-06-01T00:00:00Z", "apply": True},
        {"before": "2026-06-01T00:00:00Z", "apply": True, "expected_count": -1},
        {"before": "2026-06-01T00:00:00Z", "expected_count": -1},
    ],
)
def test_invalid_arguments_are_rejected_before_connecting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra: dict[str, object],
) -> None:
    monkeypatch.setattr(stamp, "load_config", lambda _path: pytest.fail("config was loaded"))
    monkeypatch.setattr(stamp, "DatabaseStore", lambda _url: pytest.fail("database was opened"))

    with pytest.raises(SystemExit) as exc_info:
        stamp.main(_args(tmp_path, **extra))

    assert exc_info.value.code == 2


def test_actual_update_rowcount_mismatch_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    record_id = _add_refinement(
        store,
        title="Eligible",
        refined_at=CUTOFF - timedelta(hours=1),
    )
    monkeypatch.setattr(stamp, "count_eligible", lambda _session, _cutoff: 2)

    with pytest.raises(stamp.StampCountError, match="expected 2, updated 1"):
        stamp.main(
            _args(
                tmp_path,
                before="2026-06-01T00:00:00Z",
                apply=True,
                expected_count=2,
            )
        )

    assert store.list_refinements(record_id)[0].city_id is None


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    return store


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "storage:\n"
        "  use: local\n"
        "  local:\n"
        "    type: sqlite\n"
        f"    path: {tmp_path / 'pino.sqlite'}\n",
        encoding="utf-8",
    )
    return path


def _args(
    tmp_path: Path,
    *,
    before: str,
    apply: bool = False,
    expected_count: int | None = None,
) -> list[str]:
    args = ["--config", str(_config(tmp_path)), "--before", before]
    if apply:
        args.append("--apply")
    if expected_count is not None:
        args.extend(["--expected-count", str(expected_count)])
    return args


def _add_refinement(
    store: SQLiteStore,
    *,
    title: str,
    refined_at: datetime,
    source: str = "test",
    content_kind: str = "event",
    city_id: str | None = None,
    location: str | None = None,
    schedule: dict[str, object] | None = None,
) -> str:
    inserted = store.add_record(
        Record(
            kind="event" if content_kind == "event" else "note",
            source=source,
            title=title,
            text=f"{title} text",
        )
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind=content_kind,
                summary=title,
                location=location,
                city_id=city_id,
                schedule=schedule,
                category_scores={"music": 0.5},
                refined_at=refined_at,
                debug={"raw": {"summary": title}},
                refiner="test",
            )
        ],
    )
    return inserted.record.id
