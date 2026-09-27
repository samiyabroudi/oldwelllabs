import pytest
from pydantic import TypeAdapter, ValidationError

from app.commitment import parse_commitment
from app.schemas import Commitment

validate = TypeAdapter(Commitment).validate_python

BIGINT_MAX = 2**63 - 1


@pytest.mark.parametrize(
    "text",
    [
        "$21,900,000 USD",
        "€4,304,000.29 EUR",
        "C$10,155,000 CAD",
        "1000 CHF",
        "$999,999,999,999,999.99 USD",  # largest accepted amount
        "$999999999999999 USD",
    ],
)
def test_accepts_valid_commitments(text):
    validate(text)


@pytest.mark.parametrize(
    "text",
    [
        "-$5,000 USD",  # parsing drops the sign, so this would be stored as +$5,000
        "$-5,000 USD",
        "+$5,000 USD",
        "−$5,000 USD",  # Unicode minus
        "$1,000,000,000,000,000 USD",  # 16 integer digits: cents would overflow bigint
        "$1000000000000000 USD",
        "$1.005 USD",
        "$1,000 usd",
        "lots of money",
    ],
)
def test_rejects_invalid_commitments(text):
    with pytest.raises(ValidationError):
        validate(text)


def test_largest_accepted_amount_fits_in_bigint():
    cents, _ = parse_commitment(validate("$999,999,999,999,999.99 USD"))
    assert cents <= BIGINT_MAX
