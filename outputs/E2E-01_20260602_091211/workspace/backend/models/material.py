from sqlalchemy import Column, Integer, String
from backend.database import Base

class Material(Base):
    __tablename__ = "materials"

    material_id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String, unique=True, index=True)
    material_name = Column(String, index=True)
    unit_of_measure = Column(String)