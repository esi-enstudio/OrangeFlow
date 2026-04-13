import os
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete

from app.Models.field_force import FieldForce
from app.Models.user import User
from app.Services.db_service import async_session
from app.Services.Automation.field_force_excel import process_field_force_excel, generate_ff_sample
from app.Utils.helpers import get_dms_credentials

router = Router()

class FFStates(StatesGroup):
    waiting_for_excel = State()
    search_query = State()

# --- ১. মেইন মেনু (Reply Keyboard Handler) ---
@router.message(F.text == "👥 ফিল্ড ফোর্স", flags={"permission": "manage_field_force"})
async def field_force_main(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 মেম্বার লিস্ট", callback_data="ff_list_0")
    builder.button(text="📤 এক্সেল আপলোড", callback_data="ff_upload_start")
    builder.button(text="📥 স্যাম্পল ডাউনলোড", callback_data="ff_sample_download")
    builder.button(text="🔍 মেম্বার সার্চ", callback_data="ff_search_start")
    builder.adjust(2)
    
    await message.answer("👥 **ফিল্ড ফোর্স ম্যানেজমেন্ট**\nআপনার প্রয়োজনীয় কাজটি নির্বাচন করুন:", reply_markup=builder.as_markup())

# --- ২. স্যাম্পল ডাউনলোড ---
@router.callback_query(F.data == "ff_sample_download")
async def download_sample(callback: CallbackQuery):
    file_path = "Field_Force_Sample.xlsx"
    await generate_ff_sample(file_path)
    await callback.message.answer_document(FSInputFile(file_path), caption="নিচের ফাইলটি ডাউনলোড করে ডাটা এন্ট্রি দিন এবং পুনরায় বটে আপলোড করুন।")
    if os.path.exists(file_path): os.remove(file_path)
    await callback.answer()

# --- ৩. এক্সেল আপলোড ---
@router.callback_query(F.data == "ff_upload_start", flags={"permission": "create_field_force"})
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 অনুগ্রহ করে আপনার পূরণ করা এক্সেল ফাইলটি (.xlsx) পাঠান।")
    await state.set_state(FFStates.waiting_for_excel)
    await callback.answer()

@router.message(FFStates.waiting_for_excel, F.document)
async def handle_excel(message: Message, state: FSMContext):
    if not message.document.file_name.endswith('.xlsx'):
        return await message.answer("❌ ভুল ফরম্যাট! শুধু .xlsx ফাইল পাঠান।")
    
    creds, error = await get_dms_credentials(message.from_user.id)
    if error: return await message.answer(error)

    wait_msg = await message.answer("⏳ প্রসেসিং শুরু হয়েছে...")
    file_path = f"temp_ff_{message.from_user.id}.xlsx"
    await message.bot.download(message.document, destination=file_path)

    count, err = await process_field_force_excel(file_path, creds['house_id'])
    
    if os.path.exists(file_path): os.remove(file_path)
    
    if err: await wait_msg.edit_text(f"❌ এরর: {err}")
    else: await wait_msg.edit_text(f"✅ সফল! {count}টি রেকর্ড আপডেট/ইনসার্ট হয়েছে।")
    await state.clear()

# --- ৪. লিস্ট দেখা (Pagination) ---
@router.callback_query(F.data.startswith("ff_list_"), flags={"permission": "view_field_force"})
async def list_ff(callback: CallbackQuery):
    offset = int(callback.data.split("_")[2])
    async with async_session() as session:
        res = await session.execute(select(FieldForce).limit(10).offset(offset))
        members = res.scalars().all()
        
        if not members and offset == 0:
            return await callback.message.answer("⚠️ বর্তমানে কোনো মেম্বার নেই।")
        
        builder = InlineKeyboardBuilder()
        text = "📋 **ফিল্ড ফোর্স মেম্বার তালিকা:**\n"
        for m in members:
            builder.button(text=f"👤 {m.name} ({m.code})", callback_data=f"ff_view_{m.id}")
        
        # নেভিগেশন বাটন
        nav = []
        if offset > 0: nav.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"ff_list_{offset-10}"))
        nav.append(types.InlineKeyboardButton(text="➡️", callback_data=f"ff_list_{offset+10}"))
        builder.row(*nav)
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())

# --- ৫. সিঙ্গেল ভিউ এবং ডিলিট ---
@router.callback_query(F.data.startswith("ff_view_"))
async def view_ff(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        m = await session.get(FieldForce, ff_id)
        details = (f"👤 **নাম:** {m.name}\n🔑 **কোড:** `{m.code}`\n📞 **ফোন:** {m.phone_number}\n"
                   f"🎭 **টাইপ:** {m.type}\n📍 **মার্কেট:** {m.market_type}\n✅ **স্ট্যাটাস:** {m.status}")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 ডিলিট", callback_data=f"ff_del_{m.id}")
        builder.button(text="🔙 ব্যাকে যান", callback_data="ff_list_0")
        builder.adjust(2)
        await callback.message.edit_text(details, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("ff_del_"), flags={"permission": "delete_field_force"})
async def delete_ff(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        m = await session.get(FieldForce, ff_id)
        if m:
            await session.delete(m)
            await session.commit()
            await callback.answer(f"✅ {m.name} ডিলিট করা হয়েছে।", show_alert=True)
    await list_ff(callback)