from sqlalchemy import Column, Integer, String
from backend.database import Base

class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String, unique=True, index=True)
    product_name = Column(String, index=True)
    unit_of_measure = Column(String)