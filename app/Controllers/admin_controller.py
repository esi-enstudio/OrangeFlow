from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from sqlalchemy import select
from app.Models.user import User
from app.Services.db_service import async_session
from app.Views.keyboards.reply import get_admin_main_menu, get_settings_menu
from config.settings import SUPER_ADMIN_ID

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, permissions: list = None):
    """স্টার্ট কমান্ড: ইউজার পারমিশন অনুযায়ী মেনু প্রদর্শন করবে"""
    await state.clear()
    user_id = message.from_user.id

    # ১. সুপার এডমিন চেক
    if int(user_id) == int(SUPER_ADMIN_ID):
        # সুপার এডমিনের জন্য সব পারমিশন (যাতে সব বাটন দেখা যায়)
        all_perms = ["dms_access", "manage_settings", "view_users", "view_houses"] 
        return await message.answer(
            "👋 স্বাগতম সুপার এডমিন! ❤️", 
            reply_markup=get_admin_main_menu(all_perms)
        )

    # ২. নিবন্ধিত ইউজার চেক
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user:
            # মিডলওয়্যার থেকে প্রাপ্ত permissions লিস্ট ব্যবহার করে মেনু তৈরি
            user_perms = permissions or []
            return await message.answer(
                f"👋 স্বাগতম {db_user.name}!\nআপনার অ্যাকাউন্টটি সক্রিয় আছে।",
                reply_markup=get_admin_main_menu(user_perms)
            )

    # ৩. যদি ইউজার নিবন্ধিত না হয় (অচেনা ইউজার)
    await message.answer(
        f"আপনার আইডি: `{user_id}`\n"
        "অনুগৃহ করে এই আইডি এডমিনকে দিন, যাতে আপনাকে সিস্টেমে যুক্ত করা যায়।",
        parse_mode="Markdown"
    )

@router.message(F.text == "⚙️ সেটিংস", flags={"permission": "manage_settings"})
async def settings_menu(message: Message):
    await message.answer(f"⚙️ **সিস্টেম সেটিংস**\n📅 তারিখ: {datetime.now().strftime('%d-%m-%Y')}", 
                         reply_markup=get_settings_menu(), parse_mode="Markdown")

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext, permissions: list):
    """প্রধান মেনুতে ফিরে যাওয়া (পারমিশন অনুযায়ী বাটনসহ)"""
    await state.clear()
    
    from app.Views.keyboards.reply import get_admin_main_menu
    
    await message.answer(
        "আপনি প্রধান মেনুতে ফিরে এসেছেন।", 
        reply_markup=get_admin_main_menu(permissions)
    )