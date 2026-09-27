"""Convert between commitment display strings like "$1,200,000 USD" and (cents, currency).

The trailing 3-letter code is the currency; any leading symbol ("$", "€", "C$") is
ignored. The amount is stored in hundredths of the currency unit for every currency,
JPY included (so "¥913,000,000 JPY" is 91,300,000,000). That keeps one rule for all
rows; ISO 4217 minor units (JPY has none) would be the alternative.

Decimal, never float: float can't represent most cent values exactly.
"""

import re
from decimal import Decimal

# Display symbols for the currencies in funds.csv; any other code is shown without one.
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "C$"}


def parse_commitment(text: str) -> tuple[int, str]:
    text = text.strip()
    currency = text[-3:]
    amount = Decimal(re.sub(r"[^0-9.]", "", text))
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"commitment has more than two decimal places: {text!r}")
    return int(cents), currency


def format_commitment(cents: int, currency: str) -> str:
    """Inverse of parse_commitment: (792300099, "USD") -> "$7,923,000.99 USD".

    Decimals are shown only when there are cents, matching how funds.csv writes amounts,
    so every value in the CSV round-trips to the exact same string.
    """
    units, rem = divmod(cents, 100)
    amount = f"{units:,}" if rem == 0 else f"{units:,}.{rem:02d}"
    return f"{SYMBOLS.get(currency, '')}{amount} {currency}"
