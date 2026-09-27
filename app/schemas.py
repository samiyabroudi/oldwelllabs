from typing import Annotated

from pydantic import BaseModel, StringConstraints

# e.g. "$1,200,000 USD", "€4,304,000.29 EUR", "C$10,155,000 CAD".
# Optional leading symbol, an amount with optional thousands separators and at most two
# decimals, then a space and a 3-letter currency code. Validating the shape from day one
# means every stored value is parseable when the migration later splits it into columns.
# - The symbol can't contain a sign (+, -, U+2212 minus): parsing keeps only digits and
#   the decimal point, so "-$5,000 USD" would otherwise be stored as +$5,000.
# - At most 15 integer digits, so the amount in cents always fits in a bigint (max ~9.2e18).
COMMITMENT_PATTERN = r"^[^\d+\u2212-]*(\d{1,3}(,\d{3}){0,4}|\d{1,15})(\.\d{1,2})?\s+[A-Z]{3}$"

Commitment = Annotated[str, StringConstraints(strip_whitespace=True, pattern=COMMITMENT_PATTERN)]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class FundIn(BaseModel):
    fund_name: NonEmpty
    strategy: NonEmpty
    vintage_year: int
    commitment: Commitment


class FundPatch(BaseModel):
    fund_name: NonEmpty | None = None
    strategy: NonEmpty | None = None
    vintage_year: int | None = None
    commitment: Commitment | None = None


class FundOut(BaseModel):
    id: int
    fund_name: str
    strategy: str
    vintage_year: int
    commitment: str
