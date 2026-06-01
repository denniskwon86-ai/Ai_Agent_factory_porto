from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from backend import schemas, services
from backend.database import get_db

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    """
    Create a new order with multiple order items.
    Inventory will be checked and decremented.
    """
    return services.order_service.create_order(db=db, order_create=order)

@router.get("/", response_model=List[schemas.OrderResponse])
def read_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of all orders, including their items and material names.
    """
    orders = services.order_service.get_orders(db, skip=skip, limit=limit)
    return orders

@router.get("/{order_id}", response_model=schemas.OrderResponse)
def read_order(order_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single order by ID, including its items and material names.
    """
    order = services.order_service.get_order_by_id(db, order_id=order_id)
    return order

@router.patch("/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, status_update: schemas.OrderUpdateStatus, db: Session = Depends(get_db)):
    """
    Update the status of an existing order.
    If status changes to CANCELLED, items are returned to inventory.
    """
    return services.order_service.update_order_status(db=db, order_id=order_id, status_update=status_update)

@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    """
    Delete an order. If the order was not cancelled, items are returned to inventory.
    """
    return services.order_service.delete_order(db=db, order_id=order_id)