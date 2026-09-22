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


# ============================================================
# ROUTER
# ============================================================

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
    """
    Create a new bill.

    Tenant and user IDs come from the authenticated user.

    Frontend does NOT send:
        tenant_id
        user_id
    """

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

    return BillCreateResponse(
        type="success",
        message="Bill created successfully",
        data=BillCreateResponseData(
            bill_id=bill.id,
            bill_number=bill.bill_number,
            total_amount=bill.total_amount,
            paid_amount=data.paid_amount,
            kadan_amount=kadan.get("kadan_amount") if kadan else Decimal("0"),
            payment_method=data.payment_method,
            created_at=bill.created_at,
        )
    )


# ============================================================
# GET ALL BILLS
# ============================================================

@router.get(
    "",
)
async def get_bills(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
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
# GET DATE SUMMARY
# ============================================================

@router.get(
    "/date-summary",
    response_model=DateSummaryResponse,
)
async def get_date_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
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

    return bill


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

    return bill