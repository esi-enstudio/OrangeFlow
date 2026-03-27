from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Any, Callable, Dict, Awaitable
from app.Services.db_service import async_session
from sqlalchemy import select
from app.Models.user import User
from config.settings import SUPER_ADMIN_ID


class ACLMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        # ১. সুপার এডমিন হলে সব এক্সেস পাবে
        if user_id == SUPER_ADMIN_ID:
            return await handler(event, data)

        # ২. ডাটাবেজ থেকে ইউজারের পারমিশন চেক করা
        async with async_session() as session:
            res = await session.execute(select(User).where(User.telegram_id == user_id))
            user = res.scalar_one_or_none()

            if not user or not user.role:
                # যদি ইউজার না থাকে বা রোল না থাকে
                if event.text == "/start": return await handler(event, data)
                return await event.answer("🚫 আপনার এই কমান্ড ব্যবহারের অনুমতি নেই।")

            # ইউজারের সব পারমিশন লিস্ট তৈরি
            user_permissions = [p.name for p in user.role.permissions]
            data["permissions"] = user_permissions  # হ্যান্ডলারে পারমিশন পাস করা

        return await handler(event, data)