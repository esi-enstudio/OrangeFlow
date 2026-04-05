from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.Views.keyboards.reply import get_admin_main_menu

router = Router()

@router.message(F.text == "🤖 DMS Tasks", flags={"permission": "dms_access"})
async def show_dms_tasks_menu(message: Message, permissions: list):
    builder = InlineKeyboardBuilder()
    
    if "sim_status_check" in permissions:
        builder.button(text="🔍 সিম স্ট্যাটাস চেক", callback_data="run_sim_status")
        
    if "sim_issue" in permissions:
        builder.button(text="📤 সিম ইস্যু", callback_data="run_sim_issue")
        
    if "sim_return" in permissions:
        builder.button(text="📥 সিম রিটার্ন", callback_data="run_sim_return")
    
    builder.adjust(1)
    
    if not builder.as_markup().inline_keyboard:
        return await message.answer("⚠️ আপনার কোনো টাস্ক ব্যবহারের পারমিশন নেই।")

    await message.answer(
        "🤖 **DMS অটোমেশন মেনু**\nআপনার টাস্কটি নির্বাচন করুন:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )