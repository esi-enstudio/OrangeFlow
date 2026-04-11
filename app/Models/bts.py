from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.Models.base import Base

class BTS(Base):
    __tablename__ = "bts_list"

    id = Column(Integer, primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), nullable=True)
    
    # স্ক্রিনশট অনুযায়ী কলামসমূহ
    bts_code = Column(String, unique=True, index=True) # BTS Code (DHK6400)
    thana = Column(String)
    district = Column(String)
    division = Column(String)
    region = Column(String)
    network_mode = Column(String) # 2G+4G
    address = Column(String)      # BTS Address
    cluster = Column(String)
    longitude = Column(String)
    latitude = Column(String)
    distributor_code = Column(String)
    on_air_date_2g = Column(String) # 2Gonairdate
    on_air_date_3g = Column(String) # 3Gonairdate
    on_air_date_4g = Column(String) # 4Gonairdate
    urban_rural = Column(String)
    thana_project = Column(String)
    lus = Column(String)
    sran = Column(String)
    rest = Column(String)
    union_name = Column(String)    # UNUID_Union name

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    house = relationship("House")