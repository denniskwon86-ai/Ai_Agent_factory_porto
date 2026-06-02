from pydantic import BaseModel

class MaterialBase(BaseModel):
    material_code: str
    material_name: str
    unit_of_measure: str

class MaterialCreate(MaterialBase):
    pass

class MaterialResponse(MaterialBase):
    material_id: int

    class Config:
        from_attributes = True