from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import OrderCreate, OrderUpdate, Order as OrderSchema
from backend.services import OrderService
from backend.models import OrderStatus # OrderStatus Enum import
from typing import List

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
    responses={404: {"model": dict, "description": "Not found"}},
)

@router.post("/", response_model=OrderSchema, status_code=status.HTTP_201_CREATED, summary="Create a new order")
async def create_order(
    order: OrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    새로운 주문을 생성합니다. 주문 시 재고 수량이 차감됩니다.
    """
    service = OrderService(db)
    try:
        return await service.create_order(order)
    except HTTPException as e:
        raise e
    except Exception as e:
        # 로깅 추가 권장
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/", response_model=List[OrderSchema], summary="Get a list of orders")
async def read_orders(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    모든 주문 목록을 조회합니다.
    """
    service = OrderService(db)
    orders = await service.get_orders(skip=skip, limit=limit)
    return orders

@router.get("/{order_id}", response_model=OrderSchema, summary="Get a specific order by ID")
async def read_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 주문 ID로 주문 정보를 조회합니다.
    """
    service = OrderService(db)
    try:
        return await service.get_order(order_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.patch("/{order_id}/status", response_model=OrderSchema, summary="Update order status")
async def update_order_status(
    order_id: int,
    order_update: OrderUpdate, # status 필드만 포함하는 스키마 사용
    db: AsyncSession = Depends(get_db)
):
    """
    특정 주문 ID의 상태를 업데이트합니다.
    """
    service = OrderService(db)
    try:
        # Ensure only status is passed to service
        if order_update.status is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status field is required for status update.")
        return await service.update_order_status(order_id, order_update.status)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.delete("/{order_id}", response_model=OrderSchema, summary="Delete an order by ID")
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 주문 ID로 주문을 삭제합니다.
    """
    service = OrderService(db)
    try:
        return await service.delete_order(order_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

print("Order router defined.")