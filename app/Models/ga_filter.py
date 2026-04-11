from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class GAProductFilter(Base):
    """জিএ রিপোর্ট থেকে যে প্রোডাক্ট কোডগুলো বাদ যাবে (উদা: SIMSWAP)"""
    __tablename__ = "ga_product_filters"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    product_code = Column(String, nullable=False) # উদা: ESIMSWAP
    
    created_at = Column(DateTime, server_default=func.now())
    house = relationship("House")

class GARetailerFilter(Base):
    """মার্কেট জিএ থেকে যে ধরণের রিটেইলার বাদ যাবে (উদা: DRC, BP)"""
    __tablename__ = "ga_retailer_filters"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    keyword = Column(String, nullable=False) # উদা: DRC বা BP_CODE এর অংশ
    
    created_at = Column(DateTime, server_default=func.now())
    house = relationship("House")