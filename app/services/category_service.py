from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryCreate


class CategoryService:

    def __init__(self):
        self.repository = CategoryRepository()

    # =========================================================
    # Create Category
    # =========================================================

    async def create_category(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        data: CategoryCreate,
    ) -> Category:

        try:

            name = data.name.strip()

            if not name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category name cannot be empty",
                )

            existing = await self.repository.get_by_name(
                db=db,
                tenant_id=tenant_id,
                name=name,
            )

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Category already exists",
                )

            category = Category(
                tenant_id=tenant_id,
                name=name,
                description=(
                    data.description.strip()
                    if data.description
                    else None
                ),
                status="ACTIVE",
            )

            await self.repository.create(
                db=db,
                category=category,
            )

            await db.commit()

            await db.refresh(category)

            return category

        except HTTPException:
            await db.rollback()
            raise

        except Exception:
            await db.rollback()
            raise

    # =========================================================
    # Get Shop Categories
    # =========================================================

    async def get_categories(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[Category]:

        return await self.repository.get_all(
            db=db,
            tenant_id=tenant_id,
        )


category_service = CategoryService()