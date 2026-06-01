from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from backend.models import OrderStatus

# Material Schemas
class MaterialBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class MaterialCreate(MaterialBase):
    initial_inventory_quantity: int = Field(0, ge=0, description="Initial quantity for inventory when material is created")

class MaterialResponse(MaterialBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Inventory Schemas
class InventoryBase(BaseModel):
    quantity: int = Field(..., ge=0)

class InventoryResponse(InventoryBase):
    id: int
    material_id: int
    updated_at: datetime

    class Config:
        from_attributes = True

# OrderItem Schemas
class OrderItemBase(BaseModel):
    material_id: int
    quantity: int = Field(..., gt=0)
    price_per_unit: float = Field(..., gt=0)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    id: int
    order_id: int
    material_name: Optional[str] = None # To be populated by service
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Order Schemas
class OrderBase(BaseModel):
    status: OrderStatus = OrderStatus.PENDING

class OrderCreate(BaseModel):
    order_items: List[OrderItemCreate] = Field(..., min_length=1)

class OrderUpdateStatus(BaseModel):
    status: OrderStatus

class OrderResponse(OrderBase):
    id: int
    order_date: datetime
    order_items: List[OrderItemResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True