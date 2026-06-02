from pydantic import BaseModel, EmailStr
from typing import Optional

# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str # e.g., "admin", "planner", "viewer"

class UserCreate(UserBase):
    password: str

class User(UserBase):
    user_id: int

    class Config:
        orm_mode = True

# Product Schemas
class ProductBase(BaseModel):
    product_code: str
    product_name: str
    unit_of_measure: str

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    product_id: int

    class Config:
        orm_mode = True

# Material Schemas
class MaterialBase(BaseModel):
    material_code: str
    material_name: str
    unit_of_measure: str

class MaterialCreate(MaterialBase):
    pass

class Material(MaterialBase):
    material_id: int

    class Config:
        orm_mode = True