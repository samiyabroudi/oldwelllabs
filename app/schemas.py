import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from pydantic_core import PydanticCustomError

# e.g. "$1,200,000 USD", "€4,304,000.29 EUR", "C$10,155,000 CAD".
# Optional leading symbol, an amount with optional thousands separators and at most two
# decimals, then a space and a 3-letter currency code. Validating the shape from day one
# means every stored value is parseable when the migration later splits it into columns.
# - The symbol can't contain a sign (+, -, U+2212 minus): parsing keeps only digits and
#   the decimal point, so "-$5,000 USD" would otherwise be stored as +$5,000.
# - At most 15 integer digits, so the amount in cents always fits in a bigint (max ~9.2e18).
COMMITMENT_PATTERN = r"^[^\d+\u2212-]*(\d{1,3}(,\d{3}){0,4}|\d{1,15})(\.\d{1,2})?\s+[A-Z]{3}$"



def _check_commitment(value: str) -> str:
    # A custom error instead of `pattern=`, whose message would show users the raw regex.
    if not re.fullmatch(COMMITMENT_PATTERN, value):
        raise PydanticCustomError(
            "commitment_format",
            "must look like $1,200,000 USD: optional symbol, no sign, at most 15 digits and "
            "2 decimals, then a 3-letter currency code",
        )
    return value


Commitment = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_check_commitment)]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Bounded so a huge value is a 422, not a Postgres integer overflow (500).
VintageYear = Annotated[int, Field(ge=1900, le=2100)]


class FundIn(BaseModel):
    fund_name: NonEmpty
    strategy: NonEmpty
    vintage_year: VintageYear
    commitment: Commitment


class FundPatch(BaseModel):
    # Omitted fields default to None and are left unchanged (the route dumps with
    # exclude_unset). An explicit null isn't a valid value for any field, so it's a 422
    # rather than being silently ignored.
    fund_name: NonEmpty = None
    strategy: NonEmpty = None
    vintage_year: VintageYear = None
    commitment: Commitment = None


class FundOut(BaseModel):
    id: int
    fund_name: str
    strategy: str
    vintage_year: int
    commitment: str  # display string, e.g. "$1,200,000 USD"
    commitment_cents: int  # hundredths of the currency unit, JPY included
    currency: str  # ISO 4217 code
