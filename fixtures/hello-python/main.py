"""Run this file, or place a breakpoint inside QuoteCalculator.calculate."""

from decimal import Decimal

from hello_python import QuoteCalculator, QuoteLine


def main() -> None:
    lines = [
        QuoteLine(name="Notebook", unit_price=Decimal("12.50"), quantity=2),
        QuoteLine(name="Pen", unit_price=Decimal("3.00"), quantity=3),
    ]
    quote = QuoteCalculator().calculate(lines)
    print(f"OpenPyCharm demo: subtotal={quote.subtotal:.2f}, tax={quote.tax:.2f}, total={quote.total:.2f}")


if __name__ == "__main__":
    main()
