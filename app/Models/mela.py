from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

# Pivot Table: মেলার সাথে বিটিএস লিঙ্ক করার জন্য
mela_bts_link = Table(
    'mela_bts_assignments',
    Base.metadata,
    Column('mela_id', Integer, ForeignKey('melas.id')),
    Column('bts_id', Integer, ForeignKey('bts_list.id'))
)

class Mela(Base):
    __tablename__ = "melas"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    
    activity_date = Column(Date, nullable=False, index=True)
    thana = Column(String)
    location = Column(String)
    event_type = Column(String)
    activity_type = Column(String)
    
    created_at = Column(DateTime, server_default=func.now())
    
    # রিলেশনসমূহ
    house = relationship("House")
    
    # ১. এই মেলার আন্ডারে কোন কোন BTS আছে
    covered_bts = relationship("BTS", secondary=mela_bts_link)
    
    # ২. এই মেলার আন্ডারে কোন কোন কর্মী (RSO/BP) আছে
    assignments = relationship("MelaAssignment", back_populates="mela", cascade="all, delete-orphan")

class MelaAssignment(Base):
    """মেলাতে অংশগ্রহণকারী আরএসও, বিপি বা দোকানদারদের ট্র্যাকিং"""
    __tablename__ = "mela_assignments"

    id = Column(Integer, primary_key=True)
    mela_id = Column(Integer, ForeignKey('melas.id'), nullable=False)
    
    retailer_code = Column(String, nullable=False) # R-Code (R591295 ইত্যাদি)
    role_type = Column(String)                      # RSO, BP, or SHOPKEEPER
    
    mela = relationship("Mela", back_populates="assignments")