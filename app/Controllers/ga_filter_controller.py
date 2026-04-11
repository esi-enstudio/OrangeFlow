from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete

from app.Models.ga_filter import GAProductFilter, GARetailerFilter
from app.Services.db_service import async_session
from app.Utils.helpers import get_dms_credentials # হাউজ আইডি পাওয়ার জন্য

router = Router()

class FilterStates(StatesGroup):
    waiting_for_product = State()
    waiting_for_retailer_keyword = State()

# --- ১. ফিল্টার মেইন মেনু ---
@router.message(F.text == "⚙️ জিএ ফিল্টার সেটিংস", flags={"permission": "manage_settings"})
async def ga_filter_menu(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 প্রোডাক্ট ফিল্টার", callback_data="manage_p_filters")
    builder.button(text="🔍 রিটেইলার কিওয়ার্ড ফিল্টার", callback_data="manage_r_filters")
    builder.adjust(1)
    await message.answer("🛠 **জিএ রিপোর্ট ফিল্টার সেটিংস**\nকোনটি ম্যানেজ করতে চান?", reply_markup=builder.as_markup())

# --- ২. প্রোডাক্ট ফিল্টার হ্যান্ডেলিং ---
@router.callback_query(F.data == "manage_p_filters")
async def list_product_filters(callback: CallbackQuery):
    creds, _ = await get_dms_credentials(callback.from_user.id)
    async with async_session() as session:
        res = await session.execute(select(GAProductFilter).where(GAProductFilter.house_id == creds['house_id']))
        filters = res.scalars().all()
        
        text = "🚫 **বাদ দেওয়া প্রোডাক্ট কোডসমূহ:**\n"
        builder = InlineKeyboardBuilder()
        for f in filters:
            text += f"• `{f.product_code}`\n"
            builder.button(text=f"🗑 {f.product_code}", callback_data=f"del_pf_{f.id}")
        
        builder.button(text="➕ নতুন কোড যোগ করুন", callback_data="add_product_filter")
        builder.adjust(2)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data == "add_product_filter")
async def add_pf_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("প্রোডাক্ট কোডটি লিখুন (উদা: SIMSWAP):")
    await state.set_state(FilterStates.waiting_for_product)
    await callback.answer()

@router.message(FilterStates.waiting_for_product)
async def save_product_filter(message: Message, state: FSMContext):
    creds, _ = await get_dms_credentials(message.from_user.id)
    async with async_session() as session:
        session.add(GAProductFilter(house_id=creds['house_id'], product_code=message.text.upper().strip()))
        await session.commit()
    await message.answer(f"✅ প্রোডাক্ট `{message.text}` ফিল্টারে যুক্ত হয়েছে।")
    await state.clear()

# --- ৩. রিটেইলার কিওয়ার্ড ফিল্টার হ্যান্ডেলিং ---
@router.callback_query(F.data == "manage_r_filters")
async def list_retailer_filters(callback: CallbackQuery):
    creds, _ = await get_dms_credentials(callback.from_user.id)
    async with async_session() as session:
        res = await session.execute(select(GARetailerFilter).where(GARetailerFilter.house_id == creds['house_id']))
        filters = res.scalars().all()
        
        text = "🔍 **রিটেইলার এক্সক্লুশন কিওয়ার্ডসমূহ:**\n(এই কিওয়ার্ডগুলো থাকলে মার্কেটের জিএ-তে আসবে না)\n"
        builder = InlineKeyboardBuilder()
        for f in filters:
            text += f"• `{f.keyword}`\n"
            builder.button(text=f"🗑 {f.keyword}", callback_data=f"del_rf_{f.id}")
        
        builder.button(text="➕ নতুন কিওয়ার্ড যোগ করুন", callback_data="add_retailer_filter")
        builder.adjust(2)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data == "add_retailer_filter")
async def add_rf_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("কিওয়ার্ডটি লিখুন (উদা: DRC বা BP):")
    await state.set_state(FilterStates.waiting_for_retailer_keyword)
    await callback.answer()

@router.message(FilterStates.waiting_for_retailer_keyword)
async def save_retailer_filter(message: Message, state: FSMContext):
    creds, _ = await get_dms_credentials(message.from_user.id)
    async with async_session() as session:
        session.add(GARetailerFilter(house_id=creds['house_id'], keyword=message.text.upper().strip()))
        await session.commit()
    await message.answer(f"✅ কিওয়ার্ড `{message.text}` ফিল্টারে যুক্ত হয়েছে।")
    await state.clear()

# --- ডিলিট হ্যান্ডেলার ---
@router.callback_query(F.data.startswith(("del_pf_", "del_rf_")))
async def delete_filter(callback: CallbackQuery):
    is_prod = callback.data.startswith("del_pf_")
    f_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        model = GAProductFilter if is_prod else GARetailerFilter
        await session.execute(delete(model).where(model.id == f_id))
        await session.commit()
    
    await callback.answer("🗑 ফিল্টার মুছে ফেলা হয়েছে।")
    if is_prod: await list_product_filters(callback)
    else: await list_retailer_filters(callback)