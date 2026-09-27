import pytest
from pydantic import TypeAdapter, ValidationError

from app.commitment import parse_commitment
from app.schemas import Commitment, FundIn, FundPatch

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


@pytest.mark.parametrize("year", [1900, 2012, 2100])
def test_accepts_vintage_years_in_range(year):
    FundIn(fund_name="A", strategy="B", vintage_year=year, commitment="$1 USD")


@pytest.mark.parametrize("year", [1899, 2101, -5, 99_999_999_999])  # the last overflowed integer
def test_rejects_vintage_years_out_of_range(year):
    with pytest.raises(ValidationError):
        FundIn(fund_name="A", strategy="B", vintage_year=year, commitment="$1 USD")


@pytest.mark.parametrize("field", ["fund_name", "strategy", "vintage_year", "commitment"])
def test_patch_rejects_explicit_null(field):
    with pytest.raises(ValidationError):
        FundPatch.model_validate({field: None})


def test_patch_only_includes_fields_sent():
    assert FundPatch.model_validate({"fund_name": "New"}).model_dump(exclude_unset=True) == {
        "fund_name": "New"
    }
