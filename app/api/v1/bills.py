from decimal import Decimal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.schemas.bill import (
    BillCreate,
    BillCreateResponse,
    BillCreateResponseData,
    BillResponse,
    DateSummaryResponse,
)

from app.services.billing_service import billing_service
from app.repositories.bill_repository import bill_repository


router = APIRouter(
    prefix="/bills",
    tags=["Billing"],
)


# ============================================================
# CREATE BILL
# ============================================================

@router.post(
    "",
    response_model=BillCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bill(
    data: BillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    result = await billing_service.create_bill(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        data=data,
    )

    bill = result["bill"]
    kadan = result.get("kadan")

    kadan_amount = (
        kadan.get("kadan_amount", Decimal("0.00"))
        if kadan
        else Decimal("0.00")
    )

    return BillCreateResponse(
        type="success",
        message="Bill created successfully",
        data=BillCreateResponseData(
            bill_id=bill.id,
            bill_number=bill.bill_number,
            subtotal=bill.subtotal,
            discount_amount=bill.discount_amount,
            tax_amount=bill.tax_amount,
            total_amount=bill.total_amount,
            paid_amount=data.paid_amount,
            kadan_amount=kadan_amount,
            payment_method=data.payment_method,
            created_at=bill.created_at,
        ),
    )


# ============================================================
# GET ALL BILLS
# ============================================================

@router.get("")
async def get_bills(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]

    bills = await bill_repository.get_bills(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )

    return {
        "type": "success",
        "message": "Bills fetched successfully",
        "data": bills,
    }


# ============================================================
# DATE SUMMARY
# ============================================================

@router.get(
    "/date-summary",
    response_model=DateSummaryResponse,
)
async def get_date_summary(
    date: str = Query(
        ...,
        description="Date in YYYY-MM-DD format",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]

    return await billing_service.get_date_summary(
        db=db,
        tenant_id=tenant_id,
        target_date_str=date,
    )


# ============================================================
# BUILD BILL DETAIL RESPONSE WITH KADAN
# ============================================================

async def _build_bill_detail_response(
    db: AsyncSession,
    tenant_id: UUID,
    bill,
) -> BillResponse:
    """
    Build a bill response and attach the CREDIT transaction
    associated with this bill, if one exists.

    Historical bill Kadan and current customer outstanding
    are deliberately returned as separate values.
    """

    response = BillResponse.model_validate(bill)

    transaction = (
        await bill_repository.get_kadan_details_for_bill(
            db=db,
            tenant_id=tenant_id,
            bill_id=bill.id,
        )
    )

    # No Kadan CREDIT transaction was created for this bill.
    if transaction is None:
        response.kadan = None
        return response

    # Calculate actual completed payments for this bill.
    paid_amount = sum(
        (
            Decimal(str(payment.amount))
            for payment in (bill.payments or [])
            if (payment.status or "").upper() == "COMPLETED"
        ),
        Decimal("0.00"),
    )

    account = transaction.kadan_account

    current_outstanding = (
        Decimal(str(account.outstanding_amount))
        if account is not None
        and account.outstanding_amount is not None
        else Decimal("0.00")
    )

    response.kadan = {
        "paid_amount": paid_amount,
        # Historical amount added by this bill.
        "kadan_amount": Decimal(str(transaction.amount)),
        # Existing field: now represents current account balance.
        "outstanding_amount": current_outstanding,
        "transaction_id": transaction.id,
        "account_id": transaction.kadan_account_id,
        "transaction_type": transaction.transaction_type,
        "balance_after_transaction": transaction.balance_after,
        "notes": transaction.notes,
        "created_at": transaction.created_at,
    }

    return response


# ============================================================
# GET BILL BY NUMBER
# ============================================================

@router.get(
    "/number/{bill_number}",
    response_model=BillResponse,
)
async def get_bill_by_number(
    bill_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]

    bill = await bill_repository.get_bill_by_number(
        db=db,
        tenant_id=tenant_id,
        bill_number=bill_number,
    )

    if bill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bill not found",
        )

    return await _build_bill_detail_response(
        db=db,
        tenant_id=tenant_id,
        bill=bill,
    )


# ============================================================
# GET BILL BY ID
# ============================================================

@router.get(
    "/{bill_id}",
    response_model=BillResponse,
)
async def get_bill(
    bill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]

    bill = await bill_repository.get_bill_by_id(
        db=db,
        tenant_id=tenant_id,
        bill_id=bill_id,
    )

    if bill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bill not found",
        )

    return await _build_bill_detail_response(
        db=db,
        tenant_id=tenant_id,
        bill=bill,
    )
