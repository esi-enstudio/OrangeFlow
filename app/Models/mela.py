from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

# ১. পিভট টেবিল: মেলার সাথে বিটিএস লিঙ্ক করার জন্য (এটি ক্লাসের আগে থাকতে হবে) ✅
mela_bts_link = Table(
    'mela_bts_assignments',
    Base.metadata,
    Column('mela_id', Integer, ForeignKey('melas.id'), primary_key=True),
    Column('bts_id', Integer, ForeignKey('bts_list.id'), primary_key=True)
)

# ২. মেলার ধরণ (উদা: Zoom In)
class MelaType(Base):
    __tablename__ = "mela_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

# ৩. মেলার এক্টিভটি (উদা: Local Games)
class MelaActivity(Base):
    __tablename__ = "mela_activities"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

# ৪. এলিজিবল বিটিএস লিস্ট (পিভট টেবিল) ✅
class MelaEligibleBTS(Base):
    __tablename__ = "mela_eligible_bts"
    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    bts_id = Column(Integer, ForeignKey('bts_list.id'), nullable=False)
    
    # রিলেশনশিপ
    bts = relationship("BTS") 
    house = relationship("House")

# ৫. মেলা ম্যানেজমেন্টের মূল টেবিল
class Mela(Base):
    __tablename__ = "melas"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    
    activity_date = Column(Date, nullable=False, index=True)
    thana = Column(String) # এটি bts_list থেকে অটো-পপুলেট হবে
    location = Column(String)
    
    # এখানে মেলার ধরণ ও এক্টিভিটির ID সেভ হবে ✅
    mela_type_id = Column(Integer, ForeignKey('mela_types.id'))
    mela_activity_id = Column(Integer, ForeignKey('mela_activities.id'))
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # রিলেশনসমূহ
    house = relationship("House")
    mela_type = relationship("MelaType")
    mela_activity = relationship("MelaActivity")
    
    # এই মেলার আন্ডারে কোন কোন BTS আছে ✅
    covered_bts = relationship("BTS", secondary=mela_bts_link, lazy="selectin")
    
    # এই মেলার আন্ডারে কোন কোন কর্মী আছে ✅
    assignments = relationship("MelaAssignment", back_populates="mela", cascade="all, delete-orphan", lazy="selectin")

class MelaAssignment(Base):
    """মেলাতে অংশগ্রহণকারী কর্মীদের ট্র্যাকিং (RSO, BP, SSO)"""
    __tablename__ = "mela_assignments"

    id = Column(Integer, primary_key=True)
    mela_id = Column(Integer, ForeignKey('melas.id'), nullable=False)
    
    retailer_code = Column(String, nullable=False, index=True) 
    role_type = Column(String, nullable=False) # 'RSO', 'BP', or 'SSO'
    
    mela = relationship("Mela", back_populates="assignments")