from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


#create category
class CategoryRepository:

    async def create(
        self,
        db: AsyncSession,
        category: Category,
    ) -> Category:

        db.add(category)

        await db.flush()

        return category

    async def get_by_name(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        name: str,
    ) -> Category | None:

        result = await db.execute(
            select(Category).where(
                Category.tenant_id == tenant_id,
                Category.name.ilike(name),
            )
        )

        return result.scalar_one_or_none()

#get all categories for a tenent
    async def get_all(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[Category]:

        result = await db.execute(
            select(Category)
            .where(
                Category.tenant_id == tenant_id,
                Category.status == "ACTIVE",
            )
            .order_by(Category.name.asc())
        )

        return list(result.scalars().all())


category_repository = CategoryRepository()