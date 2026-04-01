from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.Models.user import User
from app.Services.db_service import async_session

async def get_dms_credentials(telegram_id: int):
    """ইউজারের হাউজ থেকে DMS ক্রেডেনশিয়াল সংগ্রহ করার কমন ফাংশন"""
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.house)).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.house:
            return None, "❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।"

        house = user.house
        if not all([house.dms_user, house.dms_pass, house.dms_house_id]):
            return None, f"❌ হাউজ '{house.name}' এর জন্য DMS Credentials সেট করা নেই।"

        return {
            "user": house.dms_user,
            "pass": house.dms_pass,
            "house_id": house.dms_house_id,
            "house_name": house.name
        }, None