from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update as sa_update, delete as sa_delete
from fastapi import HTTPException, status
from typing import List, Optional

from backend.models import Material, Inventory, Order, OrderItem, OrderStatus
from backend.schemas import (
    MaterialCreate, MaterialUpdate,
    InventoryCreate, InventoryUpdate,
    OrderCreate, OrderUpdate,
    OrderItemCreate
)

# Base Service for common CRUD operations (optional, but good for DRY)
class BaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

# Material Service
class MaterialService(BaseService):
    async def get_material(self, material_id: int) -> Material:
        result = await self.db.execute(select(Material).filter(Material.material_id == material_id))
        material = result.scalars().first()
        if not material:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
        return material

    async def get_materials(self, skip: int = 0, limit: int = 100) -> List[Material]:
        result = await self.db.execute(select(Material).offset(skip).limit(limit))
        return result.scalars().all()

    async def create_material(self, material: MaterialCreate) -> Material:
        db_material = Material(**material.model_dump())
        self.db.add(db_material)
        await self.db.commit()
        await self.db.refresh(db_material)
        return db_material

    async def update_material(self, material_id: int, material_update: MaterialUpdate) -> Material:
        db_material = await self.get_material(material_id) # Reuses get_material for 404 check
        update_data = material_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_material, key, value)
        await self.db.commit()
        await self.db.refresh(db_material)
        return db_material

    async def delete_material(self, material_id: int) -> Material:
        db_material = await self.get_material(material_id) # Reuses get_material for 404 check
        await self.db.delete(db_material)
        await self.db.commit()
        return db_material # Return the deleted object

# Inventory Service
class InventoryService(BaseService):
    async def get_inventory_item(self, inventory_id: int) -> Inventory:
        result = await self.db.execute(
            select(Inventory).filter(Inventory.inventory_id == inventory_id).options(
                select.joinedload(Inventory.material)
            )
        )
        inventory_item = result.scalars().first()
        if not inventory_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
        return inventory_item

    async def get_inventory(self, skip: int = 0, limit: int = 100) -> List[Inventory]:
        result = await self.db.execute(
            select(Inventory).offset(skip).limit(limit).options(
                select.joinedload(Inventory.material)
            )
        )
        return result.scalars().all()

    async def create_inventory(self, inventory: InventoryCreate) -> Inventory:
        # Check if material exists
        material_service = MaterialService(self.db)
        await material_service.get_material(inventory.material_id) # Will raise 404 if not found

        db_inventory = Inventory(**inventory.model_dump())
        self.db.add(db_inventory)
        await self.db.commit()
        await self.db.refresh(db_inventory)
        return db_inventory

    async def update_inventory(self, inventory_id: int, inventory_update: InventoryUpdate) -> Inventory:
        db_inventory = await self.get_inventory_item(inventory_id)
        update_data = inventory_update.model_dump(exclude_unset=True)

        if 'material_id' in update_data:
            material_service = MaterialService(self.db)
            await material_service.get_material(update_data['material_id']) # Validate material_id

        for key, value in update_data.items():
            setattr(db_inventory, key, value)
        await self.db.commit()
        await self.db.refresh(db_inventory)
        return db_inventory

    async def delete_inventory(self, inventory_id: int) -> Inventory:
        db_inventory = await self.get_inventory_item(inventory_id)
        await self.db.delete(db_inventory)
        await self.db.commit()
        return db_inventory

# Order Service
class OrderService(BaseService):
    async def get_order(self, order_id: int) -> Order:
        result = await self.db.execute(
            select(Order).filter(Order.order_id == order_id).options(
                select.joinedload(Order.order_items).joinedload(OrderItem.material)
            )
        )
        order = result.scalars().first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        return order

    async def get_orders(self, skip: int = 0, limit: int = 100) -> List[Order]:
        result = await self.db.execute(
            select(Order).offset(skip).limit(limit).options(
                select.joinedload(Order.order_items).joinedload(OrderItem.material)
            ).order_by(Order.order_date.desc())
        )
        return result.scalars().all()

    async def create_order(self, order_create: OrderCreate) -> Order:
        material_service = MaterialService(self.db)
        inventory_service = InventoryService(self.db)
        total_amount = 0.0
        db_order_items = []

        for item_data in order_create.order_items:
            material = await material_service.get_material(item_data.material_id)
            
            # Check inventory
            inventory_result = await self.db.execute(
                select(Inventory).filter(Inventory.material_id == item_data.material_id)
            )
            inventory_item = inventory_result.scalars().first()

            if not inventory_item or inventory_item.quantity < item_data.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for material '{material.name}'. Available: {inventory_item.quantity if inventory_item else 0}, Requested: {item_data.quantity}"
                )
            
            # Deduct from inventory
            inventory_item.quantity -= item_data.quantity
            await self.db.commit() # Commit inventory change immediately or at the end of transaction

            db_order_item = OrderItem(
                material_id=item_data.material_id,
                quantity=item_data.quantity,
                unit_price=material.unit_price # Price at the time of order
            )
            db_order_items.append(db_order_item)
            total_amount += item_data.quantity * material.unit_price

        db_order = Order(
            order_items=db_order_items,
            total_amount=total_amount,
            status=OrderStatus.PENDING # Default status
        )
        self.db.add(db_order)
        await self.db.commit()
        await self.db.refresh(db_order)
        return db_order

    async def update_order_status(self, order_id: int, new_status: OrderStatus) -> Order:
        db_order = await self.get_order(order_id)
        
        if db_order.status == OrderStatus.COMPLETED and new_status == OrderStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel a completed order."
            )
        
        if db_order.status == OrderStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update a cancelled order."
            )

        db_order.status = new_status
        await self.db.commit()
        await self.db.refresh(db_order)
        return db_order

    async def delete_order(self, order_id: int) -> Order:
        db_order = await self.get_order(order_id)
        
        # If order is deleted, consider restoring inventory (business logic decision)
        # For simplicity, we'll just delete the order and its items.
        # If inventory restoration is needed, it should be implemented here.

        await self.db.delete(db_order)
        await self.db.commit()
        return db_order

print("Service layer defined.")