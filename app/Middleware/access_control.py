import logging
from datetime import datetime
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.flags import get_flag
from typing import Any, Callable, Dict, Awaitable
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Services.db_service import async_session
from app.Models.user import User
from app.Models.house import House
from app.Models.role import Role, Permission
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)

class ACLMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        # হ্যান্ডলার থেকে পারমিশন ফ্ল্যাগ নেওয়া
        required_permission = get_flag(data, "permission")
        today = datetime.now().date()

        async with async_session() as session:
            # ১. ইউজার এবং তার সকল হাউজ ও পারমিশন লোড করা
            result = await session.execute(
                select(User)
                .options(
                    selectinload(User.roles).selectinload(Role.permissions),
                    selectinload(User.houses)
                )
                .where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            # ২. সুপার এডমিন কি সব চেক বাইপাস করবে? 
            # প্রফেশনালভাবে: সুপার এডমিন সব বাটন দেখবে কিন্তু ইনভ্যালিড হাউজে কাজ করতে গেলে ওয়ার্নিং পাবে।
            is_super_admin = (int(user_id) == int(SUPER_ADMIN_ID))

            # ৩. সাধারণ ইউজারদের জন্য বেসিক রেজিস্ট্রেশন চেক
            if not is_super_admin:
                if not user:
                    if event.text == "/start": return await handler(event, data)
                    return await event.answer("🚫 আপনি নিবন্ধিত ইউজার নন। এডমিনের সাথে যোগাযোগ করুন।")
                
                # ৪. ইউজার স্ট্যাটাস চেক (Active কি না)
                if hasattr(user, 'status') and user.status != "Active":
                    return await event.answer("🚫 আপনার অ্যাকাউন্টটি বর্তমানে স্থগিত (Inactive) আছে।")

            # ৫. পারমিশন লিস্ট তৈরি
            user_permissions = []
            if is_super_admin:
                all_perms_res = await session.execute(select(Permission.name))
                user_permissions = [p[0] for p in all_perms_res.all()]
            elif user:
                for role in user.roles:
                    for perm in role.permissions:
                        user_permissions.append(perm.name)
            
            data["permissions"] = list(set(user_permissions))

            # ৬. অত্যন্ত গুরুত্বপূর্ণ: হাউজ এবং সাবস্ক্রিপশন চেক ✅
            # যদি এমন কোনো কাজ হয় যার জন্য পারমিশন লাগে (DMS Task, Report etc)
            if required_permission:
                # ইউজারের পারমিশন চেক
                if required_permission not in user_permissions:
                    return await event.answer(f"❌ আপনার এই কাজের অনুমতি নেই।")

                # যদি এটি হাউজ ভিত্তিক কোনো কাজ হয় (যেমন DMS Tasks)
                # আমরা চেক করবো ইউজারের অন্তত ১টি একটিভ এবং মেয়াদওয়ালা হাউজ আছে কি না
                if not is_super_admin:
                    active_valid_houses = [
                        h for h in user.houses 
                        if h.is_active and h.subscription_date and h.subscription_date.date() >= today
                    ]
                    
                    if not active_valid_houses:
                        return await event.answer(
                            "⚠️ আপনার হাউজের সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে অথবা হাউজটি ইন-একটিভ আছে।\n"
                            "অনুগ্রহ করে রিনিউ করতে সুপার এডমিনের সাথে যোগাযোগ করুন।"
                        )

        return await handler(event, data)