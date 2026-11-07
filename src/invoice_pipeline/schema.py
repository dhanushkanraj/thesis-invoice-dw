"""Canonical invoice schema (Pydantic).

Design rules:
- Every field is REQUIRED but may be null. null means "not printed on the invoice".
- Unknown extra keys are rejected, so unexpected LLM output is detected.
- This layer checks structure and format only. Business rules such as
  subtotal + tax == total live in a separate validation module (Phase 5).
"""
import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")
ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(description="Product or service description as printed, or null")
    quantity: float | None = Field(description="Quantity as a number, or null if not printed")
    unit_price: float | None = Field(description="Price per unit as a number, or null if not printed")
    line_total: float | None = Field(description="Total for this line as a number, or null if not printed")


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(description="Invoice number exactly as printed, or null")
    supplier_name: str | None = Field(description="Name of the company issuing the invoice, or null")
    supplier_tax_id: str | None = Field(description="Supplier VAT or tax identifier as printed, or null")
    invoice_date: str | None = Field(description="Invoice date in YYYY-MM-DD format, or null")
    due_date: str | None = Field(description="Payment due date in YYYY-MM-DD format, or null")
    currency: str | None = Field(description="ISO 4217 currency code such as EUR or USD, or null")
    subtotal: float | None = Field(description="Net total before tax as a number, or null")
    tax_amount: float | None = Field(description="Total tax amount as a number, or null")
    total_amount: float | None = Field(description="Gross total to pay as a number, or null")
    line_items: list[LineItem] = Field(description="All invoice line items; empty list if none are printed")

    @field_validator("invoice_date", "due_date")
    @classmethod
    def _check_iso_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not ISO_DATE_PATTERN.fullmatch(v):
            raise ValueError(f"date must be YYYY-MM-DD, got {v!r}")
        date.fromisoformat(v)  # rejects impossible dates such as 2025-02-30
        return v

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not CURRENCY_PATTERN.fullmatch(v):
            raise ValueError(f"currency must be 3 uppercase letters, got {v!r}")
        return v