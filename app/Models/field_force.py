from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class FieldForce(Base):
    __tablename__ = "field_forces"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    retailer_id = Column(Integer, ForeignKey('retailers.id'), nullable=True) # নিজের কোড চিহ্নিত করতে
    agency_id = Column(Integer, nullable=True) # এজেন্সির ডাটা থাকলে
    
    # বেসিক ইনফো
    code = Column(String, unique=True) # DMS Code
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True)
    personal_number = Column(String, unique=True)
    pool_number = Column(String, unique=True)
    type = Column(String) # SR or BP
    status = Column(String, default="Active") # Active or Resigned
    
    # ব্যাংক ইনফো
    bank_name = Column(String)
    bank_account = Column(String)
    branch_name = Column(String)
    routing_number = Column(String)
    
    # পার্সোনাল ডিটেইলস
    home_town = Column(String)
    emergency_contact_person_name = Column(String)
    emergency_contact_person_number = Column(String)
    relationship = Column(String)
    last_education = Column(String)
    institution_name = Column(String)
    blood_group = Column(String)
    present_address = Column(String)
    permanent_address = Column(String)
    fathers_name = Column(String)
    mothers_name = Column(String)
    religion = Column(String)
    dob = Column(String) # Date of Birth
    nid = Column(String)
    
    # প্রফেশনাল ডিটেইলস
    previous_company_name = Column(String)
    previous_company_salary = Column(String)
    motor_bike = Column(String) # Yes/No
    bicyle = Column(String) # Yes/No
    driving_license = Column(String) # Yes/No
    joining_date = Column(String)
    resigned_date = Column(String)
    market_type = Column(String) # Rural/Urban
    salary = Column(String)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    house = relationship("House")
    retailer = relationship("Retailer") # এটি রিটেইলার টেবিল তৈরির পর একটিভ হবে