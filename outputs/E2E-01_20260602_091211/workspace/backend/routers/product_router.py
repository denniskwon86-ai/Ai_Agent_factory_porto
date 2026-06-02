from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.schemas.product_schema import ProductCreate, ProductResponse
from backend.schemas.common_schema import ErrorResponse
from backend.services.product_service import product_service
from backend.core.exceptions import NotFoundException, ConflictException

router = APIRouter(
    prefix="/products",
    tags=["Products"],
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not Found"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflict"}
    }
)

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product_endpoint(product: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a new product.
    """
    return product_service.create_product(db=db, product=product)

@router.get("/", response_model=List[ProductResponse])
def read_products_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of products.
    """
    products = product_service.get_products(db, skip=skip, limit=limit)
    return products

@router.get("/{product_id}", response_model=ProductResponse)
def read_product_endpoint(product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single product by ID.
    """
    return product_service.get_product(db, product_id=product_id)