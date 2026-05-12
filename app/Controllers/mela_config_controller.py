import os
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.mela import MelaType, MelaActivity
from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session
from app.Services.Automation.mela_eligible_bts_excel import process_eligible_bts_excel
from app.Utils.helpers import bn_num
from app.Views.keyboards.reply import get_mela_settings_menu
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

class MelaConfigStates(StatesGroup):
    selected_house_id = State() # বিটিএস আপলোডের জন্য হাউজ আইডি
    waiting_for_type = State()
    waiting_for_activity = State()
    waiting_for_eligible_excel = State()

# ==========================================
# ১. মেলার সেটিংস মেইন মেনু (Reply Keyboard) ✅
# ==========================================
@router.message(F.text == "⚙️ মেলার সেটিংস", flags={"permission": "manage_mela_settings"})
async def show_mela_settings_sub_menu(message: Message, permissions: list):
    """ইউজারকে মেলার সেটিংস সাব-মেনু দেখাবে"""
    await message.answer(
        "⚙️ <b>মেলার কনফিগারেশন মেনু</b>\n\nএখান থেকে আপনি মেলার ধরণ, এক্টিভিটি তালিকা এবং "
        "কোম্পানি প্রদত্ত এলিজিবল বিটিএস লিস্ট আপডেট করতে পারবেন।",
        reply_markup=get_mela_settings_menu(permissions),
        parse_mode="HTML"
    )

# ==========================================
# ২. মেলার ধরণ যোগ করা (Reply Button) ✅
# ==========================================
@router.message(F.text == "➕ নতুন মেলার ধরণ", flags={"permission": "manage_mela_settings"})
async def add_mela_type_start(message: Message, state: FSMContext):
    await message.answer("📝 মেলার ধরণের নাম লিখুন (উদা: Zoom In):")
    await state.set_state(MelaConfigStates.waiting_for_type)

@router.message(MelaConfigStates.waiting_for_type)
async def save_mela_type(message: Message, state: FSMContext):
    name = message.text.strip()
    async with async_session() as session:
        session.add(MelaType(name=name))
        await session.commit()
    await message.answer(f"✅ মেলার ধরণ '<b>{name}</b>' সফলভাবে যুক্ত হয়েছে।", parse_mode="HTML")
    await state.clear()

# ==========================================
# ৩. নতুন এক্টিভিটি যোগ করা (Reply Button) ✅
# ==========================================
@router.message(F.text == "➕ নতুন এক্টিভিটি", flags={"permission": "manage_mela_settings"})
async def add_mela_activity_start(message: Message, state: FSMContext):
    await message.answer("🎯 এক্টিভিটির নাম লিখুন (উদা: Local Games):")
    await state.set_state(MelaConfigStates.waiting_for_activity)

@router.message(MelaConfigStates.waiting_for_activity)
async def save_mela_activity(message: Message, state: FSMContext):
    name = message.text.strip()
    async with async_session() as session:
        session.add(MelaActivity(name=name))
        await session.commit()
    await message.answer(f"✅ এক্টিভিটি '<b>{name}</b>' সফলভাবে যুক্ত হয়েছে।", parse_mode="HTML")
    await state.clear()

# ==========================================
# ৪. এলিজিবল বিটিএস আপলোড (হাউজ সিলেকশন লজিকসহ) ✅
# ==========================================
@router.message(F.text == "📤 এলিজিবল বিটিএস আপলোড", flags={"permission": "manage_mela_settings"})
async def upload_eligible_bts_start(message: Message, state: FSMContext):
    """চেক করবে ইউজারের কয়টি হাউজ আছে"""
    user_tg_id = message.from_user.id
    
    async with async_session() as session:
        is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))
        target_houses = []

        if is_super_admin:
            res = await session.execute(select(House).where(House.is_active == True, House.subscription_date >= datetime.now()))
            target_houses = res.scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )).scalar_one_or_none()
            if user: target_houses = [h for h in user.houses if h.is_active and h.subscription_date and h.subscription_date >= datetime.now()]

        if not target_houses:
            return await message.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।")

        # ১টি হাউজ থাকলে সরাসরি ফাইল চাবে
        if len(target_houses) == 1:
            await state.update_data(selected_house_id=target_houses[0].id)
            await message.answer(f"📁 <b>{target_houses[0].name}</b> এর এলিজিবল বিটিএস এক্সেল ফাইলটি পাঠান।")
            await state.set_state(MelaConfigStates.waiting_for_eligible_excel)
            return

        # একাধিক হাউজ থাকলে ইনলাইন বাটন
        builder = InlineKeyboardBuilder()
        for h in target_houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"mcfg_hsel_{h.id}")
        builder.adjust(1)
        await message.answer("কোন হাউজের এলিজিবল বিটিএস আপলোড করবেন?", reply_markup=builder.as_markup())
        await state.set_state(MelaConfigStates.selected_house_id)

# হাউজ সিলেকশন কলব্যাক হ্যান্ডেলার
@router.callback_query(F.data.startswith("mcfg_hsel_"))
async def handle_mcfg_house_selection(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    await state.update_data(selected_house_id=house_id)
    await callback.message.edit_text("📁 এখন ওই হাউজের এলিজিবল বিটিএস এক্সেল ফাইলটি (.xlsx) পাঠান।")
    await state.set_state(MelaConfigStates.waiting_for_eligible_excel)
    await callback.answer()

# ফাইল রিসিভ ও প্রসেসিং
@router.message(MelaConfigStates.waiting_for_eligible_excel, F.document)
async def handle_eligible_excel_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith('.xlsx'):
        return await message.answer("❌ শুধু .xlsx এক্সেল ফাইল গ্রহণ করা হয়।")
    
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    
    file_path = f"temp_eligible_{message.from_user.id}.xlsx"
    wait_msg = await message.answer("⏳ ফাইল প্রসেসিং শুরু হচ্ছে...")

    try:
        await message.bot.download(message.document, destination=file_path)
        
        async def progress(text):
            try: await wait_msg.edit_text(text)
            except: pass

        count, err = await process_eligible_bts_excel(file_path, house_id, progress)
        
        if err:
            await wait_msg.edit_text(f"❌ প্রসেসিং ব্যর্থ হয়েছে!\nএরর: {err}")
        else:
            await wait_msg.edit_text(f"✅ সফল! {bn_num(count)}টি বিটিএস এলিজিবল লিস্টে আপডেট হয়েছে।")

    except Exception as e:
        await wait_msg.edit_text(f"❌ সিস্টেম এরর: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        await state.clear()