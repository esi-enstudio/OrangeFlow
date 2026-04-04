from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session

async def get_dms_credentials(house_id: int):
    """হাউজ আইডি দিয়ে ডিএমএস ক্রেডেনশিয়াল সংগ্রহ করার কমন ফাংশন"""
    async with async_session() as session:
        # সরাসরি হাউজ টেবিল থেকে আইডি দিয়ে ডাটা নেওয়া হচ্ছে
        house = await session.get(House, house_id)
        
        if not house:
            return None, "❌ হাউজটি খুঁজে পাওয়া যায়নি।"

        # প্রয়োজনীয় ডিএমএস তথ্যগুলো আছে কি না চেক করা
        if not all([house.dms_user, house.dms_pass, house.dms_house_id]):
            return None, f"❌ হাউজ '{house.name}' এর জন্য DMS Credentials সেট করা নেই।"

        return {
            "user": house.dms_user,
            "pass": house.dms_pass,
            "house_id": house.dms_house_id,
            "house_name": house.name,
            "code": house.code
        }, None

async def get_user_houses(telegram_id: int):
    """ইউজারের সাথে যুক্ত সকল হাউজ লিস্ট পাওয়ার ফাংশন"""
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return [], "❌ ইউজার খুঁজে পাওয়া যায়নি।"
        
        if not user.houses:
            return [], "❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।"

        return user.houses, None