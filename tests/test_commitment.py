import csv

import pytest

from app.commitment import format_commitment, parse_commitment
from app.seed import CSV_PATH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$21,900,000 USD", (2_190_000_000, "USD")),
        ("$7,923,000.99 USD", (792_300_099, "USD")),
        ("€4,304,000.29 EUR", (430_400_029, "EUR")),
        ("£17,940,000 GBP", (1_794_000_000, "GBP")),
        ("C$10,155,000 CAD", (1_015_500_000, "CAD")),  # multi-char symbol is ignored
        ("¥913,000,000 JPY", (91_300_000_000, "JPY")),  # hundredths for JPY too
        ("$1.5 USD", (150, "USD")),
        ("  $1,000 USD  ", (100_000, "USD")),
    ],
)
def test_parses_amount_and_currency(text, expected):
    assert parse_commitment(text) == expected


def test_rejects_sub_cent_amounts():
    with pytest.raises(ValueError):
        parse_commitment("$1.005 USD")


@pytest.mark.parametrize(
    ("cents", "currency", "expected"),
    [
        (2_190_000_000, "USD", "$21,900,000 USD"),
        (792_300_099, "USD", "$7,923,000.99 USD"),
        (430_400_029, "EUR", "€4,304,000.29 EUR"),
        (1_015_500_000, "CAD", "C$10,155,000 CAD"),
        (91_300_000_000, "JPY", "¥913,000,000 JPY"),
        (150, "USD", "$1.50 USD"),
        (5, "USD", "$0.05 USD"),
        (100_000, "CHF", "1,000 CHF"),  # no known symbol
    ],
)
def test_formats_cents_and_currency(cents, currency, expected):
    assert format_commitment(cents, currency) == expected


def test_every_csv_value_round_trips():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        values = [row["commitment"] for row in csv.DictReader(f)]
    assert values
    for text in values:
        assert format_commitment(*parse_commitment(text)) == text


@pytest.mark.parametrize("currency", ["CHF", "USD"])
def test_formatted_output_parses_back(currency):
    assert parse_commitment(format_commitment(123_456_789, currency)) == (123_456_789, currency)
