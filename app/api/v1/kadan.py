from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.schemas.kadan import (
    KadanSummaryResponse,
    KadanAccountResponse,
    CustomerKadanResponse,
    KadanTransactionResponse,
    KadanTransactionDetailResponse,
    KadanPaymentCreate,
    KadanPaymentResponse,
)

from app.services.kadan_service import (
    kadan_service,
)


router = APIRouter(
    prefix="/kadan",
    tags=["Kadan"],
)


# ============================================================
# KADAN SUMMARY
# ============================================================

@router.get(
    "/summary",
    response_model=KadanSummaryResponse,
)
async def get_kadan_summary(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    result = await kadan_service.get_summary(
        db=db,
        tenant_id=tenant_id,
    )

    return result


# ============================================================
# ALL KADAN ACCOUNTS
# ============================================================

@router.get(
    "/accounts",
    response_model=list[KadanAccountResponse],
)
async def get_kadan_accounts(
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

    result = await kadan_service.get_accounts(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )

    return result


# ============================================================
# CUSTOMER KADAN ACCOUNT
# ============================================================

@router.get(
    "/customer/{customer_id}",
    response_model=CustomerKadanResponse,
)
async def get_customer_kadan(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    result = await kadan_service.get_customer_account(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )

    return result


# ============================================================
# CUSTOMER KADAN TRANSACTIONS
# ============================================================

@router.get(
    "/customer/{customer_id}/transactions",
    response_model=list[KadanTransactionResponse],
)
async def get_customer_kadan_transactions(
    customer_id: UUID,
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

    result = await kadan_service.get_customer_transactions(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )

    return result


# ============================================================
# SINGLE TRANSACTION
# ============================================================

@router.get(
    "/transactions/{transaction_id}",
    response_model=KadanTransactionDetailResponse,
)
async def get_kadan_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    result = await kadan_service.get_transaction(
        db=db,
        tenant_id=tenant_id,
        transaction_id=transaction_id,
    )

    return result


# ============================================================
# RECEIVE KADAN PAYMENT
# ============================================================

@router.post(
    "/customer/{customer_id}/payment",
    response_model=KadanPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def receive_kadan_payment(
    customer_id: UUID,
    data: KadanPaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    result = await kadan_service.receive_payment(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        user_id=user_id,
        data=data,
    )

    return result