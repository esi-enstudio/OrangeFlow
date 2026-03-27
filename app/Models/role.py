from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.Models.base import Base

# ১. Role এবং Permission এর মধ্যে পিভট টেবিল
role_permissions = Table(
    'roles_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id')),
    Column('permission_id', Integer, ForeignKey('permissions.id'))
)


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

    # রিলেশনশিপ (Permission এর সাথে)
    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")

    # রিলেশনশিপ (User এর সাথে - Many-to-Many)
    # এখানে 'secondary' হিসেবে user_roles ব্যবহার করতে হবে যা user.py তে আছে
    # ডাইরেক্ট ইম্পোর্ট এরর এড়াতে আমরা স্ট্রিং রেফারেন্স ব্যবহার করছি
    from app.Models.user import user_roles  # লোকাল ইম্পোর্ট সার্কুলার এরর এড়াতে
    users = relationship("User", secondary=user_roles, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)