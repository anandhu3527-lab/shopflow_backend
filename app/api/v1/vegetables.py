from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.vegetable_item import VegetableItem
from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.payment import Payment
from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction
from app.repositories.bill_repository import bill_repository
from app.schemas.vegetable import VegetableCreate, VegetableUpdate, VegetableBillCreate, VegetableResponse

router = APIRouter(prefix="/vegetables", tags=["Vegetables"])
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


async def vegetable_response(db, row):
    product = await db.get(Product, row.product_id)
    return {
        "id": row.id, "product_id": row.product_id,
        "name": product.name if product else "Unknown product",
        "unit": row.unit, "price_per_kg": row.price_per_kg,
        "tax_rate": row.tax_rate, "stock_kg": row.stock_kg,
        "status": row.status, "created_at": row.created_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=VegetableResponse)
async def create_vegetable(
    data: VegetableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER"])),
):
    tenant_id = current_user["tenant_id"]
    product_result = await db.execute(select(Product).where(
        Product.id == data.product_id, Product.tenant_id == tenant_id, Product.status == "ACTIVE"
    ))
    product = product_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Active product not found for this shop.")
    variants_result = await db.execute(select(func.count(ProductVariant.id)).where(
        ProductVariant.product_id == product.id, ProductVariant.tenant_id == tenant_id
    ))
    if variants_result.scalar_one() > 0:
        raise HTTPException(409, "This product already has variants. Use the standard product billing endpoint.")
    existing = await db.execute(select(VegetableItem).where(
        VegetableItem.tenant_id == tenant_id, VegetableItem.product_id == product.id
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "This product is already configured as a vegetable.")
    row = VegetableItem(
        tenant_id=tenant_id, product_id=product.id, unit=data.unit,
        price_per_kg=data.price_per_kg, tax_rate=data.tax_rate,
        stock_kg=data.stock_kg, status="ACTIVE"
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return await vegetable_response(db, row)


@router.get("", response_model=list[VegetableResponse])
async def list_vegetables(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(VegetableItem).where(
        VegetableItem.tenant_id == current_user["tenant_id"]
    ).order_by(VegetableItem.created_at.desc()))
    rows = result.scalars().all()
    return [await vegetable_response(db, row) for row in rows]


@router.patch("/{vegetable_id}", response_model=VegetableResponse)
async def update_vegetable(
    vegetable_id: UUID,
    data: VegetableUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER"])),
):
    result = await db.execute(select(VegetableItem).where(
        VegetableItem.id == vegetable_id,
        VegetableItem.tenant_id == current_user["tenant_id"]
    ).with_for_update())
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Vegetable not found.")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return await vegetable_response(db, row)


@router.post("/bills", status_code=status.HTTP_201_CREATED)
async def create_vegetable_bill(
    data: VegetableBillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a normal ShopFlow bill with weight-based vegetable line items (no product variants)."""
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]
    method = data.payment_method.strip().upper()
    paid = money(data.paid_amount)
    discount = money(data.discount_amount)
    customer_name = (data.customer_name or "").strip() or None
    phone = (data.customer_phone or "").strip().replace(" ", "").replace("-", "") or None
    if phone and phone.startswith("+91"):
        phone = phone[3:]
    if bool(customer_name) != bool(phone):
        raise HTTPException(400, "Customer name and phone must be provided together.")
    if phone and not re.fullmatch(r"[6-9][0-9]{9}", phone):
        raise HTTPException(400, "A valid 10-digit Indian phone number is required.")

    ids = [line.vegetable_id for line in data.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "Duplicate vegetable lines are not allowed; combine their weight.")
    result = await db.execute(select(VegetableItem, Product).join(
        Product, Product.id == VegetableItem.product_id
    ).where(
        VegetableItem.id.in_(ids),
        VegetableItem.tenant_id == tenant_id,
        VegetableItem.status == "ACTIVE",
        Product.tenant_id == tenant_id,
        Product.status == "ACTIVE",
    ).with_for_update())
    records = result.all()
    if len(records) != len(ids):
        raise HTTPException(400, "One or more vegetables were not found or are inactive.")
    by_id = {v.id: (v, p) for v, p in records}
    subtotal = ZERO
    tax_total = ZERO
    prepared = []
    for line in data.items:
        veg, product = by_id[line.vegetable_id]
        weight = Decimal(str(line.weight_kg)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if weight <= 0:
            raise HTTPException(400, "Vegetable weight must be greater than zero.")
        stock = Decimal(str(veg.stock_kg))
        if stock < weight:
            raise HTTPException(400, f"Insufficient stock for {product.name}. Available: {stock} kg.")
        # API accepts weight in kg. Price is stored as price per kg.
        gross = money(Decimal(str(veg.price_per_kg)) * weight)
        rate = Decimal(str(veg.tax_rate or 0))
        tax = money(gross * rate / Decimal("100"))
        line_total = money(gross + tax)
        subtotal += gross
        tax_total += tax
        prepared.append((veg, product, weight, gross, rate, tax, line_total))
    subtotal = money(subtotal)
    tax_total = money(tax_total)
    if discount > subtotal:
        raise HTTPException(400, "Discount cannot exceed vegetable subtotal.")
    total = money(subtotal + tax_total - discount)
    if paid > total:
        raise HTTPException(400, "Paid amount cannot exceed final bill total.")
    if method == "KADAN" and paid != ZERO:
        raise HTTPException(400, "KADAN payment requires paid_amount to be 0.")
    if method in {"CASH", "UPI"} and total > ZERO and paid <= ZERO:
        raise HTTPException(400, f"{method} payment requires a positive paid amount.")
    outstanding = money(max(total - paid, ZERO))
    if outstanding > ZERO and (not customer_name or not phone):
        raise HTTPException(400, f"Unpaid balance ₹{outstanding:.2f}; customer name and phone are required for Kadan.")

    customer = None
    if phone:
        customer = await bill_repository.get_customer_by_phone(db, tenant_id, phone)
        if customer is None:
            customer = await bill_repository.create_customer(db, tenant_id, customer_name, phone)

    latest = await bill_repository.get_latest_bill_number(db, tenant_id)
    bill_number = f"BILL-{(latest or 0) + 1:06d}"
    bill = Bill(
        tenant_id=tenant_id, customer_id=customer.id if customer else None,
        bill_number=bill_number, subtotal=subtotal, discount_amount=discount,
        tax_amount=tax_total, total_amount=total, status="COMPLETED", created_by=user_id,
    )
    try:
        await bill_repository.create_bill(db, bill)
        for veg, product, weight, gross, rate, tax, line_total in prepared:
            db.add(BillItem(
                bill_id=bill.id, product_id=product.id, product_variant_id=None,
                item_name=product.name, quantity=weight, unit_price=veg.price_per_kg,
                offer_price=None, discount_amount=ZERO, tax_rate=rate,
                tax_amount=tax, line_total=line_total,
            ))
            veg.stock_kg = Decimal(str(veg.stock_kg)) - weight
        if paid > ZERO:
            await bill_repository.create_payment(db, Payment(
                tenant_id=tenant_id, bill_id=bill.id, amount=paid,
                payment_method=method, status="COMPLETED", created_by=user_id,
            ))
        kadan_summary = None
        if outstanding > ZERO:
            account = await bill_repository.get_kadan_account(
                db, tenant_id, customer.id, for_update=True
            )
            if account is None:
                account = KadanAccount(
                    tenant_id=tenant_id, customer_id=customer.id,
                    outstanding_amount=ZERO, status="ACTIVE"
                )
                db.add(account)
                await db.flush()
            new_balance = money(Decimal(str(account.outstanding_amount or ZERO)) + outstanding)
            account.outstanding_amount = new_balance
            account.status = "ACTIVE"
            txn = KadanTransaction(
                tenant_id=tenant_id, kadan_account_id=account.id, bill_id=bill.id,
                transaction_type="CREDIT", amount=outstanding,
                balance_after=new_balance, created_by=user_id,
            )
            db.add(txn)
            kadan_summary = {"kadan_amount": outstanding, "outstanding_amount": new_balance}
        await db.commit()
        await db.refresh(bill)
        return {
            "type": "success", "message": "Vegetable bill created successfully",
            "data": {
                "bill_id": str(bill.id), "bill_number": bill.bill_number,
                "subtotal": str(subtotal), "tax_amount": str(tax_total),
                "discount_amount": str(discount), "total_amount": str(total),
                "paid_amount": str(paid), "kadan_amount": str(outstanding),
                "payment_method": method, "kadan": kadan_summary,
                "items": [
                    {"product_id": str(p.id), "name": p.name, "weight_kg": str(w),
                     "price_per_kg": str(v.price_per_kg), "tax_rate": str(rate),
                     "tax_amount": str(tax), "line_total": str(lt)}
                    for v, p, w, gross, rate, tax, lt in prepared
                ],
            }
        }
    except Exception:
        await db.rollback()
        raise
