import os
import asyncio
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session
from app.Services.Automation.activation_excel import process_activation_excel
from app.Views.keyboards.reply import get_data_center_menu
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

class ActivationStates(StatesGroup):
    selected_house_id = State()
    waiting_for_activations = State()

# ==========================================
# ডাটা সেন্টার মেইন গেটওয়ে (Reply Keyboard) ✅
# ==========================================
@router.message(F.text == "💾 ডাটা সেন্টার", flags={"permission": "manage_data_center"})
async def show_data_center(message: Message, permissions: list):
    """ইউজার যখন কিবোর্ড থেকে '💾 ডাটা সেন্টার' চাপ দিবে"""

    await message.answer(
        "💾 <b>ডাটা সেন্টার ম্যানেজমেন্ট</b>\n\n"
        "এখান থেকে আপনি হাউজ ভিত্তিক ডাটাবেজ আপডেট করতে পারবেন। "
        "কোন মডিউলটি আপডেট করতে চান নির্বাচন করুন:",
        reply_markup=get_data_center_menu(permissions),
        parse_mode="HTML"
    )


# ==========================================
# মডিউল এন্ট্রি (Reply Button: 📈এক্টিভেশন)
# ==========================================
@router.message(F.text == "📈 এক্টিভেশন", flags={"permission": "manage_data_center"})
async def start_activation_upload_process(message: Message, state: FSMContext):
    await state.clear()
    user_tg_id = message.from_user.id
    
    async with async_session() as session:
        is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))
        target_houses = []

        if is_super_admin:
            # সুপার এডমিন সব হাউজ দেখবে
            res = await session.execute(select(House).where(House.is_active == True, House.subscription_date >= datetime.now()))
            target_houses = res.scalars().all()
        else:
            # সাধারণ ইউজার তার লিঙ্ক করা হাউজগুলো দেখবে
            u_res = await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )
            user = u_res.scalar_one_or_none()
            if user: target_houses = [h for h in user.houses if h.is_active and h.subscription_date and h.subscription_date >= datetime.now()]

        if not target_houses:
            return await message.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।")

        # ১টি হাউজ থাকলে সরাসরি ফাইল চাবে
        if len(target_houses) == 1:
            house = target_houses[0]
            await state.update_data(selected_house_id=house.id, house_name=house.name)
            await message.answer(f"📁 <b>{house.name}</b> এর জন্য এক্টিভেশন এক্সেল ফাইলটি পাঠান।", parse_mode="HTML")
            await state.set_state(ActivationStates.waiting_for_activations)
            return

        # একাধিক হাউজ থাকলে সিলেকশন বাটন
        builder = InlineKeyboardBuilder()
        for h in target_houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"act_hsel_{h.id}")
        builder.adjust(1)
        await message.answer("🎯 এক্টিভেশন আপলোড করার জন্য <b>হাউজ নির্বাচন করুন:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.set_state(ActivationStates.selected_house_id)


# ==========================================
# হাউজ সিলেকশন হ্যান্ডেলার (Callback)
# ==========================================
@router.callback_query(F.data.startswith("act_hsel_"), ActivationStates.selected_house_id)
async def handle_act_house_selection(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house: return await callback.answer("হাউজ পাওয়া যায়নি")
        
        await state.update_data(selected_house_id=house.id, house_name=house.name)
        await callback.message.edit_text(f"🏢 হাউজ: <b>{house.name}</b>\n\nএখন ওই হাউজের এক্টিভেশন এক্সেল ফাইলটি পাঠান।", parse_mode="HTML")
        await state.set_state(ActivationStates.waiting_for_activations)
    await callback.answer()

# ==========================================
# ফাইল রিসিভ এবং প্রসেসিং ✅
# ==========================================
@router.message(ActivationStates.waiting_for_activations, F.document)
async def handle_activation_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith('.xlsx'):
        return await message.answer("❌ ভুল ফাইল! শুধু .xlsx এক্সেল ফাইল পাঠান।")
    
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    h_name = data.get('house_name')

    file_path = f"temp_ga_{message.from_user.id}.xlsx"
    wait_msg = await message.answer(f"⏳ <b>{h_name}</b> এর ফাইল প্রসেসিং শুরু হচ্ছে...", parse_mode="HTML")

    try:
        await message.bot.download(message.document, destination=file_path)
        
        async def progress(text):
            try: await wait_msg.edit_text(text, parse_mode="HTML")
            except: pass

        count, err = await process_activation_excel(file_path, house_id, progress)
        
        if err:
            await wait_msg.edit_text(f"❌ <b>প্রসেসিং ব্যর্থ!</b>\nএরর: `{err}`", parse_mode="HTML")
        else:
            await wait_msg.edit_text(
                f"✅ <b>সফলভাবে আপলোড সম্পন্ন!</b>\n\n"
                f"🏢 হাউজ: <b>{h_name}</b>\n"
                f"📊 মোট রেকর্ড: <code>{bn_num(count)}</code> টি",
                parse_mode="HTML"
            )
    except Exception as e:
        await wait_msg.edit_text(f"❌ এরর: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        await state.clear()