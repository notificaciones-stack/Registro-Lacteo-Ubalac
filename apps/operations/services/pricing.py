from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from ..models import PurchaseTerms


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def snapshot_terms(producer):
    adjustments = [{"id": str(p.pk), "name": p.name, "kind": p.kind, "rate": str(p.rate)} for p in producer.deductions.filter(active=True).order_by("pk")]
    for price in producer.product_prices.select_related("product"):
        previous = PurchaseTerms.objects.filter(producer=producer, product=price.product).first()
        if not previous or previous.unit_price != price.unit_price or previous.adjustments != adjustments:
            PurchaseTerms.objects.create(producer=producer, product=price.product, unit_price=price.unit_price, adjustments=adjustments)


def terms_at(producer, product, collected_at):
    terms = PurchaseTerms.objects.filter(producer=producer, product=product, effective_from__lte=collected_at).first()
    # Missing historical terms must never be silently repriced using today's price.
    return (terms.unit_price, terms.adjustments) if terms else (None, [])


def receipt_amounts(receipt, liters=None):
    liters = liters if liters is not None else getattr(receipt, "effective_liters", receipt.liters)
    if receipt.unit_price is None:
        return {"gross": Decimal("0"), "deductions": Decimal("0"), "taxes": Decimal("0"), "net": Decimal("0"), "lines": [], "priced": False}
    gross = money(liters * receipt.unit_price)
    lines = [{**p, "amount": money(gross * Decimal(p["rate"]) / 100)} for p in receipt.adjustments]
    deductions = sum((p["amount"] for p in lines if p["kind"] == "WITHHOLDING"), Decimal("0"))
    taxes = sum((p["amount"] for p in lines if p["kind"] == "TAX"), Decimal("0"))
    return {"gross": gross, "deductions": deductions, "taxes": taxes, "net": gross - deductions + taxes, "lines": lines, "priced": True}


def financial_summary(receipts):
    totals = {key: Decimal("0") for key in ("gross", "deductions", "taxes", "net")}
    totals.update(unpriced=0, unpriced_liters=Decimal("0"))
    rows, adjustments = {}, defaultdict(lambda: {"amount": Decimal("0"), "name": "", "rate": "", "kind": ""})
    for receipt in receipts:
        if receipt.status != "CONFIRMED":
            continue
        amounts = receipt_amounts(receipt)
        receipt.amounts = amounts
        key = (receipt.producer_id, receipt.product_id)
        row = rows.setdefault(key, {"producer": receipt.producer, "product": receipt.product, "liters": Decimal("0"), "count": 0, "unpriced": 0, **{k: Decimal("0") for k in ("gross", "deductions", "taxes", "net")}})
        row["liters"] += getattr(receipt, "effective_liters", receipt.liters)
        row["count"] += 1
        for k in ("gross", "deductions", "taxes", "net"):
            row[k] += amounts[k]
            totals[k] += amounts[k]
        if not amounts["priced"]:
            row["unpriced"] += 1
            totals["unpriced"] += 1
            totals["unpriced_liters"] += getattr(receipt, "effective_liters", receipt.liters)
        for p in amounts["lines"]:
            group = adjustments[(p["id"], p["name"], p["rate"], p["kind"])]
            group.update(name=p["name"], rate=p["rate"], kind=p["kind"])
            group["amount"] += p["amount"]
    return {"financial": totals, "financial_rows": list(rows.values()), "adjustment_totals": list(adjustments.values())}
