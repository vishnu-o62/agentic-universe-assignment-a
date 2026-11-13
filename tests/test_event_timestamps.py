import pytest

from solution.ingestion.event_ingestion import normalize_event_timestamp


def test_naive_timestamp_is_interpreted_as_ist():
    result = normalize_event_timestamp("2026-10-14T12:00:00")
    assert result == "2026-10-14T06:30:00+00:00"


def test_utc_z_timestamp():
    result = normalize_event_timestamp("2026-10-14T12:00:00Z")
    assert result == "2026-10-14T12:00:00+00:00"


def test_offset_timestamp_converted_to_utc():
    result = normalize_event_timestamp("2026-10-14T12:00:00+05:30")
    assert result == "2026-10-14T06:30:00+00:00"


def test_empty_timestamp_returns_none():
    assert normalize_event_timestamp("") is None
    assert normalize_event_timestamp(None) is None


def test_invalid_timestamp_raises_error():
    with pytest.raises(ValueError):
        normalize_event_timestamp("not-a-timestamp")
