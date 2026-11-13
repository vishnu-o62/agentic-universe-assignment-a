import pytest

from solution.utils.normalization import (
    clean_text,
    normalize_phone,
    normalize_date,
    normalize_decimal,
    normalize_enum,
)


def test_clean_text():
    assert clean_text("  hello  ") == "hello"
    assert clean_text("   ") is None
    assert clean_text(None) is None


@pytest.mark.parametrize("phone, expected", [
    ("9876543210", "+919876543210"),
    ("+91 98765 43210", "+919876543210"),
    ("919876543210", "+919876543210"),
    ("09876543210", "+919876543210"),
])
def test_valid_phone_numbers(phone, expected):
    assert normalize_phone(phone) == expected


@pytest.mark.parametrize("phone", [
    None,
    "",
    "1234567890",
    "5876543210",
    "987654321",
    "987654321012",
])
def test_invalid_phone_numbers(phone):
    assert normalize_phone(phone) is None


@pytest.mark.parametrize("date, expected", [
    ("2026-10-14", "2026-10-14"),
    ("14/10/2026", "2026-10-14"),
    ("14-10-2026", "2026-10-14"),
    ("14-Oct-2026", "2026-10-14"),
    ("14-oct-2026", "2026-10-14"),
])
def test_valid_dates(date, expected):
    assert normalize_date(date) == expected


@pytest.mark.parametrize("date", [
    "2026-02-30",
    "31/13/2026",
    "invalid-date",
])
def test_invalid_dates(date):
    with pytest.raises(ValueError):
        normalize_date(date)


@pytest.mark.parametrize("value, expected", [
    ("₹1,250", "1250.00"),
    ("Rs. 1,250.50", "1250.50"),
    ("INR 500", "500.00"),
    ("250.456", "250.46"),
    ("0", "0.00"),
])
def test_valid_decimals(value, expected):
    assert normalize_decimal(value) == expected


@pytest.mark.parametrize("value", [
    "-100",
    "abc",
    "₹",
])
def test_invalid_decimals(value):
    with pytest.raises(ValueError):
        normalize_decimal(value)


def test_enum_normalization():
    assert normalize_enum(" English ", ["en", "hi"]) == "en"
    assert normalize_enum("HINDI", ["en", "hi"]) == "hi"
    assert normalize_enum("EN", ["en", "hi"]) == "en"


def test_invalid_enum():
    with pytest.raises(ValueError):
        normalize_enum("French", ["en", "hi"])
