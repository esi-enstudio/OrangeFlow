from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.dispatcher.flags import get_flag
from typing import Any, Callable, Dict, Awaitable
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.Services.db_service import async_session
from app.Models.user import User
from config.settings import SUPER_ADMIN_ID

class ACLMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # ১. হ্যান্ডলার থেকে পারমিশন ফ্ল্যাগ চেক করা (যেমন: view_houses)
        required_permission = get_flag(data, "permission")
        
        # যদি কোনো পারমিশন দরকার না হয় (যেমন: পাবলিক কমান্ড), তবে সরাসরি পাস করবে
        if not required_permission:
            return await handler(event, data)

        user_id = event.from_user.id

        # ২. সুপার এডমিন চেক (সুপার এডমিনের সব পারমিশন আছে)
        if int(user_id) == int(SUPER_ADMIN_ID):
            return await handler(event, data)

        # ৩. ডাটাবেজ থেকে ইউজার এবং তার পারমিশন লোড করা
        async with async_session() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.role).selectinload(r.permissions)) # গভীর থেকে লোড করা
                .where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            # ইউজার বা রোল না থাকলে ব্লক করা
            if not user or not user.role:
                return await event.answer("🚫 আপনি নিবন্ধিত ইউজার নন। এডমিনের সাথে যোগাযোগ করুন।")

            # ইউজারের পারমিশন লিস্ট তৈরি
            user_permissions = [p.name for p in user.role.permissions]
            
            # ৪. কাঙ্খিত পারমিশন চেক করা
            if required_permission not in user_permissions:
                return await event.answer(f"❌ আপনার এই কাজটি করার পারমিশন নেই। (প্রয়োজন: {required_permission})")

        # সব ঠিক থাকলে হ্যান্ডলার কল করা
        return await handler(event, data)