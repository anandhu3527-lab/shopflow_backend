from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.schemas.category import CategoryCreate, CategoryResponse
from app.services.category_service import category_service


router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


# =========================================================
# Create Category
# =========================================================

@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER"])),
):

    tenant_id = current_user["tenant_id"]

    category = await category_service.create_category(
        db=db,
        tenant_id=tenant_id,
        data=data,
    )

    return category


# =========================================================
# Get Shop Categories
# =========================================================

@router.get(
    "",
    response_model=list[CategoryResponse],
)
async def get_categories(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    categories = await category_service.get_categories(
        db=db,
        tenant_id=tenant_id,
    )

    return categories