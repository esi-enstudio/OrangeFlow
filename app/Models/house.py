from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base
from app.Models.user import user_houses

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

    # DMS Credentials
    dms_user = Column(String, nullable=True)
    dms_pass = Column(String, nullable=True)
    dms_house_id = Column(String, nullable=True)

    subscription_date = Column(DateTime)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # User মডেলের সাথে রিলেশন
    users = relationship(
        "User", 
        secondary=user_houses, # এটি যোগ করা বাধ্যতামূলক ✅
        back_populates="houses"
    )
    
    retailers = relationship("Retailer", back_populates="house")