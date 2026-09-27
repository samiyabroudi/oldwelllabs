"""Parse commitment display strings like "$1,200,000 USD" into (cents, currency).

The trailing 3-letter code is the currency; any leading symbol ("$", "€", "C$") is
ignored. The amount is stored in hundredths of the currency unit for every currency,
JPY included (so "¥913,000,000 JPY" is 91,300,000,000). That keeps one rule for all
rows; ISO 4217 minor units (JPY has none) would be the alternative.

Decimal, never float: float can't represent most cent values exactly.
"""

import re
from decimal import Decimal


def parse_commitment(text: str) -> tuple[int, str]:
    text = text.strip()
    currency = text[-3:]
    amount = Decimal(re.sub(r"[^0-9.]", "", text))
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"commitment has more than two decimal places: {text!r}")
    return int(cents), currency
