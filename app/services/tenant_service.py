from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant_repository import tenant_repository


class TenantService:
    """
    Service for tenant-related business logic.
    """

    async def get_tenant_me(
        self,
        db: AsyncSession,
        current_user: dict,
    ) -> dict:
        """
        Fetch the current tenant (shop) details and all its employees.
        Requires the user to be an OWNER.
        """
        # ============================================================
        # 1. OWNER AUTHORIZATION
        # ============================================================
        
        role = current_user["role"]
        if role.name != "OWNER":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the shop owner can access this information",
            )
            
        # ============================================================
        # 2. EXTRACT AUTHENTICATED CONTEXT
        # ============================================================
        
        tenant = current_user["tenant"]
        user_id = current_user["user_id"]
        tenant_id = current_user["tenant_id"]

        # ============================================================
        # 3. FETCH ALL USERS FOR THE TENANT
        # ============================================================
        
        users_with_roles = await tenant_repository.get_tenant_users_with_roles(
            db=db,
            tenant_id=tenant_id,
        )

        # ============================================================
        # 4. SEPARATE OWNER AND EMPLOYEES
        # ============================================================
        
        owner_data = None
        employees_list = []

        for u, r in users_with_roles:
            employee_dict = {
                "id": str(u.id),
                "name": u.name,
                "phone": u.phone,
                "status": u.status,
                "role": r.name,
                "created_at": u.created_at,
            }

            if u.id == user_id:
                owner_data = employee_dict
            else:
                employees_list.append(employee_dict)

        # Fallback if owner is somehow not in the joined query (should not happen)
        if not owner_data:
            u_current = current_user["user"]
            owner_data = {
                "id": str(u_current.id),
                "name": u_current.name,
                "phone": u_current.phone,
                "status": u_current.status,
                "role": role.name,
                "created_at": u_current.created_at,
            }

        # ============================================================
        # 5. CONSTRUCT RESPONSE
        # ============================================================
        
        return {
            "type": "success",
            "message": "Shop details fetched successfully",
            "data": {
                "shop": {
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "business_name": tenant.business_name,
                    "phone": tenant.phone,
                    "email": tenant.email,
                    "address": tenant.address,
                    "status": tenant.status,
                    "created_at": tenant.created_at,
                    "updated_at": tenant.updated_at,
                },
                "owner": owner_data,
                "employees": employees_list,
            }
        }

    async def update_tenant(
        self,
        db: AsyncSession,
        current_user: dict,
        update_data,
    ) -> dict:
        """
        Update the current tenant (shop) details.
        Requires the user to be an OWNER.
        """
        role = current_user["role"]
        if role.name != "OWNER":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the shop owner can update shop details",
            )
            
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )
            
        tenant = current_user["tenant"]
        
        old_values = {}
        new_values = {}
        
        for key, value in update_dict.items():
            old_val = getattr(tenant, key, None)
            if old_val != value:
                old_values[key] = old_val
                new_values[key] = value
            setattr(tenant, key, value)
            
        if new_values:
            from app.services.audit_service import log as audit_log
            await audit_log(
                db=db,
                tenant_id=tenant.id,
                user_id=current_user["user_id"],
                action="SHOP_UPDATED",
                entity_type="tenant",
                entity_id=tenant.id,
                description=f"Shop {tenant.name} updated",
                old_values=old_values,
                new_values=new_values,
            )
            
        await db.commit()
        await db.refresh(tenant)

        return {
            "type": "success",
            "message": "Shop details updated successfully",
            "data": {
                "shop": {
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "business_name": tenant.business_name,
                    "phone": tenant.phone,
                    "email": tenant.email,
                    "address": tenant.address,
                    "status": tenant.status,
                    "created_at": tenant.created_at,
                    "updated_at": tenant.updated_at,
                }
            }
        }

tenant_service = TenantService()
