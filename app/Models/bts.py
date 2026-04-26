from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class BTS(Base):
    __tablename__ = "bts_list"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=False)
    
    # এক্সেল হেডার অনুযায়ী কলামসমূহ
    site_id = Column(String, unique=True, index=True) # Site ID
    bts_code = Column(String, unique=True, index=True) # BTS Code
    site_type = Column(String)                        # Site Type
    thana = Column(String)                            # Thana
    thana_bn = Column(String)                         # Thana Bn
    district = Column(String)                         # District
    district_bn = Column(String)                      # District Bn
    division = Column(String)                         # Division
    division_bn = Column(String)                      # Division Bn
    cluster = Column(String)                          # Cluster
    cluster_bn = Column(String)                       # Cluster Bn
    region = Column(String)                           # Region
    region_bn = Column(String)                         # Region Bn
    network_mode = Column(String)                     # Network Mode
    address = Column(String)                          # Address
    address_bn = Column(String)                       # Address Bn
    short_address = Column(String)                    # Short Address
    longitude = Column(String)
    latitude = Column(String)
    archetype = Column(String)                        # Archetype
    market = Column(String)                           # Market
    distributor_code = Column(String)                 # Distributor Code
    onair_date_2g = Column(String)                    # 2Gonairdate
    onair_date_3g = Column(String)                    # 3Gonairdate
    onair_date_4g = Column(String)                    # 4Gonairdate
    urban_rural = Column(String)                      # Urban_Rural
    priority = Column(String)                         # Priority

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    house = relationship("House")