from sqlalchemy import Column, Integer, String
from backend.database import Base # Assuming Base is defined in backend/database.py

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, index=True) # e.g., "admin", "planner", "viewer"