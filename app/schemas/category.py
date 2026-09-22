from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# CREATE CATEGORY
# ============================================================

class CategoryCreate(BaseModel):

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )


# ============================================================
# CATEGORY RESPONSE
# ============================================================

class CategoryResponse(BaseModel):

    id: UUID
    name: str
    description: str | None
    status: str

    model_config = {
        "from_attributes": True
    }


# ============================================================
# CATEGORY LIST RESPONSE
# ============================================================

class CategoryListResponse(BaseModel):

    categories: list[CategoryResponse]