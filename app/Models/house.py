from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.Models.base import Base

class House(Base):
    __tablename__ = "houses"

    id = Column(Integer, primary_key=True, index=True)
    cluster = Column(String)
    region = Column(String)
    name = Column(String)
    code = Column(String, unique=True)
    email = Column(String)
    address = Column(String)
    contact = Column(String)
    subscription_date = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())