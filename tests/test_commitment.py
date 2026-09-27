import pytest

from app.commitment import parse_commitment


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
