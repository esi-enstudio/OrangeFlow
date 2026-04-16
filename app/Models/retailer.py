from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class Retailer(Base):
    __tablename__ = "retailers"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    field_force_id = Column(Integer, ForeignKey('field_forces.id'), nullable=True)

    # আপনার দেওয়া নির্দিষ্ট কলামসমূহ
    retailer_code = Column(String, unique=True, index=True) # RETAILER_CODE
    name = Column(String, nullable=False)          # RETAILER_NAME
    type = Column(String)                          # RETAILER_TYPE
    enabled = Column(String)                       # ENABLED (Yes/No)
    sim_seller = Column(String)                    # SIM_SELLER
    tran_mobile_no = Column(String)                # TRANMOBILENO
    itop_sr_number = Column(String)                # I_TOP_UP_SR_NUMBER
    itop_number = Column(String)                   # I_TOP_UP_NUMBER
    service_point = Column(String)                 # SERVICE_POINT
    category = Column(String)                      # CATEGORY
    owner_name = Column(String)                    # OWNER_NAME
    contact_no = Column(String)                    # CONTACT_NO
    district = Column(String)                      # DISTRICT
    thana = Column(String)                         # THANA
    address = Column(String)                       # ADDRESS
    nid = Column(String)                           # NID
    bp_code = Column(String)                       # BP_CODE
    bp_number = Column(String)                     # BP_NUMBER
    dob = Column(String)                           # DOB
    route = Column(String)                         # ROUTE

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # হাউজের সাথে রিলেশন
    house = relationship("House", back_populates="retailers")

    # রিলেশন: এই রিটেইলারের অধীনে কতগুলো লাইভ এক্টিভেশন আছে
    activations = relationship("LiveActivation", back_populates="retailer")

    field_force = relationship("FieldForce", back_populates="retailers")
