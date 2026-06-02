from pydantic import BaseModel

class ProductBase(BaseModel):
    product_code: str
    product_name: str
    unit_of_measure: str

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    product_id: int

    class Config:
        from_attributes = True