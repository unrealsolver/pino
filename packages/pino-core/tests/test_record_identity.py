from pino_core.models import Record, compute_record_fingerprint


def test_record_fingerprint_prefers_external_id() -> None:
    first = Record(
        kind="event",
        source="source",
        external_id="abc",
        title="Old title",
        text="Old text",
    )
    second = Record(
        kind="event",
        source="source",
        external_id="abc",
        title="New title",
        text="New text",
    )

    assert compute_record_fingerprint(first) == compute_record_fingerprint(second)


def test_record_fingerprint_normalizes_url_tracking_params() -> None:
    first = Record(
        kind="event",
        source="source",
        text="Text",
        url="HTTPS://Example.com/Event/?utm_source=test",
    )
    second = Record(
        kind="event",
        source="source",
        text="Different text",
        url="https://example.com/Event",
    )

    assert compute_record_fingerprint(first) == compute_record_fingerprint(second)

