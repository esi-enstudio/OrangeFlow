from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.dispatcher.flags import get_flag
from typing import Any, Callable, Dict, Awaitable
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.Services.db_service import async_session
from app.Models.user import User
from app.Models.role import Role, Permission
from app.Models.field_force import FieldForce
from config.settings import SUPER_ADMIN_ID

class ACLMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        required_permission = get_flag(data, "permission")

        # ১. সুপার এডমিনের জন্য সব পারমিশন লোড করা
        if int(user_id) == int(SUPER_ADMIN_ID):
            async with async_session() as session:
                # সিস্টেমের সব পারমিশন নাম নিয়ে আসা
                all_perms_res = await session.execute(select(Permission.name))
                all_perms = [p[0] for p in all_perms_res.all()]
                data["permissions"] = all_perms # সুপার এডমিনকে সব পারমিশন দিয়ে দেওয়া হলো
            return await handler(event, data)

        # ২. সাধারণ ইউজারের জন্য ডাটাবেজ থেকে চেক করা
        async with async_session() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.roles).selectinload(Role.permissions))
                .where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user or not user.roles:
                # /start কমান্ড ছাড়া অন্য কিছু হলে আটকে দিবে
                if event.text == "/start": return await handler(event, data)
                return await event.answer("🚫 আপনি নিবন্ধিত নন অথবা আপনার কোনো রোল নেই।")

            # ইউজারের সব রোল থেকে পারমিশনগুলো সংগ্রহ করা
            user_permissions = []
            for role in user.roles:
                for perm in role.permissions:
                    user_permissions.append(perm.name)
            
            data["permissions"] = list(set(user_permissions)) # ডুপ্লিকেট বাদ দিয়ে ডাটাতে পাঠানো

            # ৩. যদি ফ্ল্যাগ থাকে, তবে পারমিশন চেক করা
            if required_permission and required_permission not in user_permissions:
                return await event.answer(f"❌ আপনার এই কাজের অনুমতি নেই। (প্রয়োজন: {required_permission})")

        return await handler(event, data)


async def is_owner(user_id, target_ff_id):
    """চেক করবে এই ইউজার কি ওই ফিল্ড ফোর্স প্রোফাইলের মালিক কি না"""
    async with async_session() as session:
        res = await session.execute(
            select(FieldForce.id).where(FieldForce.user_id == user_id, FieldForce.id == target_ff_id)
        )
        return res.scalar_one_or_none() is not None