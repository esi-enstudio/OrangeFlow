from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
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
    # মিডলওয়্যার থেকে প্রাপ্ত permissions লিস্ট (না থাকলে খালি লিস্ট)
    user_perms = permissions or []

    # ১. সুপার এডমিন চেক
    if int(user_id) == int(SUPER_ADMIN_ID):
        return await message.answer(
            "👋 স্বাগতম সুপার এডমিন! ❤️", 
            reply_markup=get_admin_main_menu(user_perms)
        )

    # ২. নিবন্ধিত ইউজার চেক
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user:
            # মেইন মেনু কিবোর্ড জেনারেট করা
            kb = get_admin_main_menu(user_perms)
            
            if kb:
                # যদি ইউজারের অন্তত একটি পারমিশন থাকে
                return await message.answer(
                    f"👋 স্বাগতম {db_user.name}!\nআপনার অ্যাকাউন্টটি সক্রিয় আছে।",
                    reply_markup=kb
                )
            else:
                # যদি ইউজারের কোনো পারমিশন না থাকে (যেমন নতুন বিপি)
                return await message.answer(
                    f"👋 স্বাগতম {db_user.name}!\n\n"
                    "⚠️ **অনুমতি প্রয়োজন!**\n"
                    "সিস্টেমে আপনার রোলের অধীনে কোনো পারমিশন সেট করা নেই। "
                    "অনুগ্রহ করে সুপার এডমিনের সাথে যোগাযোগ করুন যাতে তিনি আপনাকে প্রয়োজনীয় পারমিশন দিতে পারেন।",
                    reply_markup=ReplyKeyboardRemove(), # কিবোর্ড সরিয়ে দিবে
                    parse_mode="Markdown"
                )

    # ৩. যদি ইউজার নিবন্ধিত না হয় (অচেনা ইউজার)
    await message.answer(
        f"আপনার আইডি: `{user_id}`\n"
        "অনুগৃহ করে এই আইডি এডমিনকে দিন, যাতে আপনাকে সিস্টেমে যুক্ত করা যায়।",
        reply_markup=ReplyKeyboardRemove(), # অচেনা ইউজারদের কিবোর্ড রিমুভ করবে
        parse_mode="Markdown"
    )

@router.message(F.text == "⚙️ সেটিংস", flags={"permission": "manage_settings"})
async def settings_menu(message: Message, permissions: list):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID) or "manage_settings" in permissions:

        await message.answer(
            f"⚙️ **সিস্টেম সেটিংস**\n\n"
            f"👑 সুপার এডমিন আইডি: `{SUPER_ADMIN_ID}`\n"
            f"🤖 বট স্ট্যাটাস: অনলাইন ✅\n"
            f"📅 আজকের তারিখ: {datetime.now().strftime('%d-%m-%Y')}",
            # এখানে permissions পাস করুন
            reply_markup=get_settings_menu(permissions), 
            parse_mode="Markdown"
        )

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext, permissions: list):
    """প্রধান মেনুতে ফিরে যাওয়া (পারমিশন অনুযায়ী বাটনসহ)"""
    await state.clear()
    
    from app.Views.keyboards.reply import get_admin_main_menu
    
    await message.answer(
        "আপনি প্রধান মেনুতে ফিরে এসেছেন।", 
        reply_markup=get_admin_main_menu(permissions)
    )