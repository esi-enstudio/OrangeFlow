from sqlalchemy import Column, Integer, String, BigInteger, Table, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.Models.base import Base

# পিভট টেবিল (User <-> Role) - এটি অবশ্যই ক্লাসের আগে থাকতে হবে
user_roles = Table(
    'users_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('role_id', Integer, ForeignKey('roles.id'))
)

# পিভট টেবিল (User <-> House)
user_houses = Table(
    'users_houses',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE")),
    Column('house_id', Integer, ForeignKey('houses.id', ondelete="CASCADE"))
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    status = Column(String, default="Active", nullable=False) # Active অথবা Inactive

    # মেনি-টু-মেনি রিলেশনশিপ (রোল টেবিলের সাথে)
    roles = relationship("Role", secondary=user_roles, back_populates="users", lazy="selectin")

    # হাউজের সাথে রিলেশনশিপ
    houses = relationship("House", secondary=user_houses, back_populates="users", lazy="selectin")

    # ফিল্ড ফোর্স এর সাথে রিলেশনশিপ
    field_force_profile = relationship("FieldForce", back_populates="user", uselist=False)

    # টাইমস্ট্যাম্প কলাম (যেখানে ভুলটি হচ্ছিল)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())