from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class LiveActivation(Base):
    __tablename__ = "live_activations"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    retailer_id = Column(Integer, ForeignKey('retailers.id'), nullable=True)
    
    # activation data columns
    activation_date = Column(String)
    activation_time = Column(String)
    retailer_code = Column(String)
    retailer_name = Column(String)
    bts_code = Column(String)
    thana = Column(String)
    promotion = Column(String)
    product_code = Column(String)
    product_name = Column(String)
    sim_no = Column(String, unique=True, index=True) # Unique ID for comparison
    msisdn = Column(String)
    selling_price = Column(String)
    bp_flag = Column(String)
    bp_number = Column(String)
    fc_bts_code = Column(String)
    bio_bts_code = Column(String)
    dh_lifting_date = Column(String)
    issue_date = Column(String)
    subscription_type = Column(String)
    service_class = Column(String)
    customer_second_contact = Column(String)
    
    created_at = Column(DateTime, server_default=func.now())

    house = relationship("House")
    retailer = relationship("Retailer", back_populates="activations")