# backend/routers/__init__.py
from . import material_router
from . import inventory_router
from . import order_router

__all__ = ["material_router", "inventory_router", "order_router"]
print("Routers initialized.")