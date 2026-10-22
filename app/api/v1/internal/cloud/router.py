from fastapi import APIRouter, Depends

from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.audit_logs import router as audit_logs_router
from app.api.v1.internal.cloud.billing import router as billing_router
from app.api.v1.internal.cloud.customers import router as customers_router
from app.api.v1.internal.cloud.overview import router as overview_router
from app.api.v1.internal.cloud.products import router as products_router
from app.api.v1.internal.cloud.shops import router as shops_router
from app.api.v1.internal.cloud.subscriptions import router as subscriptions_router
from app.api.v1.internal.cloud.support import router as support_router
from app.api.v1.internal.cloud.usage import router as usage_router
from app.api.v1.internal.cloud.users import router as users_router

router = APIRouter(
    dependencies=[Depends(verify_cloud_service_token)],
)

# A. Overview Dashboard
router.include_router(overview_router)

# B. Shop Management
router.include_router(shops_router)

# C. Shop User Management
router.include_router(users_router)

# D. Product and Inventory Management
router.include_router(products_router)

# E. Customer Management
router.include_router(customers_router)

# F. Billing & Bills
router.include_router(billing_router)

# G. Subscription Management
router.include_router(subscriptions_router)

# H. Audit Logs, Usage, Support
router.include_router(audit_logs_router)
router.include_router(usage_router)
router.include_router(support_router)
