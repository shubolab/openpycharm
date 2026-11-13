"""Small, inspectable business logic with useful debugger locals."""

from collections.abc import Iterable
from decimal import Decimal, ROUND_HALF_UP

from .models import Quote, QuoteLine

CENT = Decimal("0.01")


class QuoteCalculator:
    def __init__(self, tax_rate: Decimal = Decimal("0.06")) -> None:
        if not tax_rate.is_finite() or not Decimal("0") <= tax_rate <= Decimal("1"):
            raise ValueError("Tax rate must be between zero and one")
        self.tax_rate = tax_rate

    def calculate(self, lines: Iterable[QuoteLine]) -> Quote:
        subtotal = sum((line.amount for line in lines), start=Decimal("0"))
        subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)
        tax = (subtotal * self.tax_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        return Quote(subtotal=subtotal, tax=tax)
