"""A dependency-free project for exercising the native Python IDE."""

from .calculator import QuoteCalculator
from .models import Quote, QuoteLine

__all__ = ["Quote", "QuoteCalculator", "QuoteLine"]
