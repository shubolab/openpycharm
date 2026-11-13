"""Typed values used by the quote calculator."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class QuoteLine:
    name: str
    unit_price: Decimal
    quantity: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("An item needs a name")
        if not self.unit_price.is_finite() or self.unit_price < 0:
            raise ValueError("Unit price must be finite and nonnegative")
        if type(self.quantity) is not int or self.quantity < 1:
            raise ValueError("Quantity must be a positive integer")

    @property
    def amount(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Quote:
    subtotal: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax
