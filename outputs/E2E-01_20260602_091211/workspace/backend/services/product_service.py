from sqlalchemy.orm import Session
from backend.models.product import Product
from backend.schemas.product_schema import ProductCreate
from backend.core.exceptions import NotFoundException, ConflictException

class ProductService:
    def get_product(self, db: Session, product_id: int) -> Product:
        product = db.query(Product).filter(Product.product_id == product_id).first()
        if not product:
            raise NotFoundException(detail=f"Product with id {product_id} not found")
        return product

    def get_product_by_code(self, db: Session, product_code: str) -> Product:
        product = db.query(Product).filter(Product.product_code == product_code).first()
        if not product:
            raise NotFoundException(detail=f"Product with code {product_code} not found")
        return product

    def get_products(self, db: Session, skip: int = 0, limit: int = 100) -> list[Product]:
        return db.query(Product).offset(skip).limit(limit).all()

    def create_product(self, db: Session, product: ProductCreate) -> Product:
        db_product = db.query(Product).filter(Product.product_code == product.product_code).first()
        if db_product:
            raise ConflictException(detail=f"Product with code {product.product_code} already exists")
        
        db_product = Product(
            product_code=product.product_code,
            product_name=product.product_name,
            unit_of_measure=product.unit_of_measure
        )
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product

product_service = ProductService()