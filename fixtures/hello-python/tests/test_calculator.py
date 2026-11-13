from decimal import Decimal
import unittest

from hello_python import QuoteCalculator, QuoteLine


class QuoteCalculatorTest(unittest.TestCase):
    def test_quote_preserves_decimal_money(self) -> None:
        lines = [QuoteLine("Notebook", Decimal("12.50"), 2), QuoteLine("Pen", Decimal("3.00"), 3)]
        quote = QuoteCalculator().calculate(lines)
        self.assertEqual(quote.subtotal, Decimal("34.00"))
        self.assertEqual(quote.tax, Decimal("2.04"))
        self.assertEqual(quote.total, Decimal("36.04"))

    def test_tax_rounds_half_up_to_a_cent(self) -> None:
        quote = QuoteCalculator(Decimal("0.05")).calculate([QuoteLine("Card", Decimal("0.10"))])
        self.assertEqual(quote.tax, Decimal("0.01"))

    def test_empty_quote_has_zero_total(self) -> None:
        self.assertEqual(QuoteCalculator().calculate([]).total, Decimal("0.00"))

    def test_accepts_a_generator(self) -> None:
        lines = (QuoteLine("Sticker", Decimal("0.10")) for _ in range(3))
        self.assertEqual(QuoteCalculator(Decimal("0")).calculate(lines).total, Decimal("0.30"))

    def test_negative_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unit price"):
            QuoteLine("Invalid", Decimal("-1"))

    def test_nonfinite_price_is_rejected(self) -> None:
        for price in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(price=price), self.assertRaisesRegex(ValueError, "Unit price"):
                QuoteLine("Invalid", Decimal(price))

    def test_quantity_must_be_a_positive_integer(self) -> None:
        for quantity in (0, -1, True, 1.5):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(ValueError, "Quantity"):
                QuoteLine("Invalid", Decimal("1"), quantity)

    def test_name_cannot_be_blank(self) -> None:
        with self.assertRaisesRegex(ValueError, "name"):
            QuoteLine("  ", Decimal("1"))

    def test_invalid_tax_rate_is_rejected(self) -> None:
        for rate in ("-0.01", "1.01", "NaN", "Infinity"):
            with self.subTest(rate=rate), self.assertRaisesRegex(ValueError, "Tax rate"):
                QuoteCalculator(Decimal(rate))


if __name__ == "__main__":
    unittest.main()
