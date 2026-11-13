import json
import pytest

from solution.reporting.report_generator import (
    determine_bucket,
    get_effective_disposition,
)


METADATA = {
    "motor_renewal": {
        "renewed": {"is_terminal": True, "is_success": True},
        "payment_link_sent": {"is_terminal": False, "is_success": False},
        "not_interested": {"is_terminal": True, "is_success": False},
        "callback_requested": {"is_terminal": False, "is_success": False},
    }
}


def make_event(event_id, event_type, timestamp, code):
    return {
        "id": event_id,
        "event_type": event_type,
        "occurred_at": timestamp,
        "payload_json": json.dumps({"disposition_code": code}),
    }


def test_no_calls_bucket():
    assert determine_bucket([]) == "yet_to_reach_out"


def test_completed_bucket_has_priority():
    calls = [
        {"is_terminal": False, "telephony_failed": True},
        {"is_terminal": True, "telephony_failed": False},
    ]
    assert determine_bucket(calls) == "completed"


def test_all_calls_telephony_failed():
    calls = [
        {"is_terminal": False, "telephony_failed": True},
        {"is_terminal": False, "telephony_failed": True},
    ]
    assert determine_bucket(calls) == "in_progress_telephony_failed"


def test_mixed_telephony_failure_bucket():
    calls = [
        {"is_terminal": False, "telephony_failed": True},
        {"is_terminal": False, "telephony_failed": False},
    ]
    assert determine_bucket(calls) == "in_progress_dialed"


def test_normal_dialed_bucket():
    calls = [
        {"is_terminal": False, "telephony_failed": False},
    ]
    assert determine_bucket(calls) == "in_progress_dialed"


def test_latest_disposition_set_selected():
    events = [
        make_event(1, "disposition.set", "2026-10-14T10:00:00Z", "callback_requested"),
        make_event(2, "disposition.set", "2026-10-14T11:00:00Z", "renewed"),
    ]

    assert get_effective_disposition(
        events, METADATA, "motor_renewal"
    ) == ("renewed", True, True)


def test_override_takes_priority_over_later_set():
    events = [
        make_event(1, "disposition.override", "2026-10-14T09:00:00Z", "renewed"),
        make_event(2, "disposition.set", "2026-10-14T12:00:00Z", "not_interested"),
    ]

    assert get_effective_disposition(
        events, METADATA, "motor_renewal"
    ) == ("renewed", True, True)


def test_latest_override_selected():
    events = [
        make_event(1, "disposition.override", "2026-10-14T09:00:00Z", "renewed"),
        make_event(2, "disposition.override", "2026-10-14T11:00:00Z", "not_interested"),
    ]

    assert get_effective_disposition(
        events, METADATA, "motor_renewal"
    ) == ("not_interested", True, False)


def test_no_disposition_returns_none():
    assert get_effective_disposition(
        [], METADATA, "motor_renewal"
    ) == (None, False, False)


def test_unknown_disposition_is_ignored():
    events = [
        make_event(1, "disposition.set", "2026-10-14T10:00:00Z", "unknown_code"),
    ]

    assert get_effective_disposition(
        events, METADATA, "motor_renewal"
    ) == (None, False, False)


def test_invalid_payload_returns_none():
    event = {
        "id": 1,
        "event_type": "disposition.set",
        "occurred_at": "2026-10-14T10:00:00Z",
        "payload_json": "{invalid json",
    }

    assert get_effective_disposition(
        [event], METADATA, "motor_renewal"
    ) == (None, False, False)
