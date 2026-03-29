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
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if int(user_id) == int(SUPER_ADMIN_ID):
        return await message.answer("👋 স্বাগতম সুপার এডমিন! ❤️", reply_markup=get_admin_main_menu())
    
    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if db_user:
            return await message.answer(f"👋 স্বাগতম {db_user.name}!\nআপনার অ্যাকাউন্টটি সক্রিয় আছে।")
    
    await message.answer(f"আপনার আইডি: `{user_id}`\nএডমিনকে দিন।", parse_mode="Markdown")

@router.message(F.text == "⚙️ সেটিংস", flags={"permission": "manage_settings"})
async def settings_menu(message: Message):
    await message.answer(f"⚙️ **সিস্টেম সেটিংস**\n📅 তারিখ: {datetime.now().strftime('%d-%m-%Y')}", 
                         reply_markup=get_settings_menu(), parse_mode="Markdown")

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("প্রধান মেনু:", reply_markup=get_admin_main_menu())