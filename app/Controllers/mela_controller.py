from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.Services.Automation.Reports.mela_excel import process_mela_excel
from app.Utils.helpers import get_dms_credentials

router = Router()

class MelaStates(StatesGroup):
    waiting_for_excel = State()

@router.message(F.text == "🎪 মেলা ম্যানেজমেন্ট", flags={"permission": "manage_mela"})
async def mela_main_menu(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 আজকের মেলার লিস্ট", callback_data="mela_list_today")
    builder.button(text="📤 মেলার ফাইল আপলোড", callback_data="mela_upload")
    builder.adjust(1)
    await message.answer("🎪 **মেলার তথ্য ব্যবস্থাপনা**", reply_markup=builder.as_markup())

@router.callback_query(F.data == "mela_upload")
async def mela_upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 মেলার এক্সেল ফাইলটি পাঠান।")
    await state.set_state(MelaStates.waiting_for_excel)
    await callback.answer()

@router.message(MelaStates.waiting_for_excel, F.document)
async def handle_mela_file(message: Message, state: FSMContext):
    creds, _ = await get_dms_credentials(message.from_user.id)
    file_path = f"temp_mela_{message.from_user.id}.xlsx"
    await message.bot.download(message.document, destination=file_path)
    
    count, err = await process_mela_excel(file_path, creds['house_id'])
    
    import os
    if os.path.exists(file_path): os.remove(file_path)
    
    if err: await message.answer(f"❌ এরর: {err}")
    else: await message.answer(f"✅ সফল! {count}টি মেলার ডাটা এন্ট্রি হয়েছে।")
    await state.clear()