from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.schemas.customer import (
    CustomerListResponse,
    CustomerDetailResponse,
    CustomerBillResponse,
    CustomerCreditBillResponse,
)

from app.services.customer_service import customer_service


router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)


@router.get(
    "",
    response_model=list[CustomerListResponse],
)
async def get_customers(
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

    customers = await customer_service.get_customers(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )

    return customers


@router.get(
    "/{customer_id}",
    response_model=CustomerDetailResponse,
)
async def get_customer_detail(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user["tenant_id"]

    result = await customer_service.get_customer_detail(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )

    return result


@router.get(
    "/{customer_id}/bills",
    response_model=list[CustomerBillResponse],
)
async def get_customer_bills(
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

    result = await customer_service.get_customer_bills(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )

    return result


@router.get(
    "/{customer_id}/credit-bills",
    response_model=list[CustomerCreditBillResponse],
)
async def get_customer_credit_bills(
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

    result = await customer_service.get_customer_credit_bills(
        db=db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )

    return result