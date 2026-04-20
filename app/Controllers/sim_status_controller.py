import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# প্রোজেক্টের মডেল, সার্ভিস ও ইউটিলস ইম্পোর্ট
from app.Models.user import User as DBUser # মডেল রিনেম করা হয়েছে সংঘাত এড়াতে
from app.Models.house import House
from app.Services.db_service import async_session
from app.Services.Automation.Tasks.sim_status import run_sim_status_check
from app.Utils.validators import validate_and_expand_serials
from app.Utils.helpers import get_dms_credentials, bn_num
from config.settings import SUPER_ADMIN_ID

router = Router()

# এই ফাইলের নিজস্ব স্টেট
class SIMStatusForm(StatesGroup):
    serials = State()

# --- ১. ইনলাইন বাটন থেকে টাস্ক শুরু (হাউজ সিলেকশন লজিকসহ) ---
@router.callback_query(F.data == "run_sim_status", flags={"permission": "sim_status_check"})
async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_tg_id = callback.from_user.id
    is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

    async with async_session() as session:
        target_houses = []

        if is_super_admin:
            # সুপার এডমিন হলে ডাটাবেজের সব হাউজ লোড করবে ✅
            res = await session.execute(select(House))
            target_houses = res.scalars().all()
        else:
            # সাধারণ ইউজার হলে শুধু তার সাথে লিঙ্ক করা হাউজগুলো নিবে
            res = await session.execute(
                select(DBUser).options(selectinload(DBUser.houses)).where(DBUser.telegram_id == user_tg_id)
            )
            user = res.scalar_one_or_none()
            if user:
                target_houses = user.houses

        if not target_houses:
            return await callback.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।", show_alert=True)

        # যদি হাউজ মাত্র ১টি হয় - সরাসরি সিরিয়াল চাবে
        if len(target_houses) == 1:
            house = target_houses[0]
            await state.update_data(selected_house_id=house.id)
            await callback.message.answer(
                f"🏢 হাউজ: **{house.display_name}**\n\nসিম সিরিয়াল অথবা রেঞ্জ (Start-End) লিখে পাঠান:",
                parse_mode="Markdown"
            )
            await state.set_state(SIMStatusForm.serials)
        
        # যদি একাধিক হাউজ থাকে - সিলেকশন মেনু দেখাবে ✅
        else:
            builder = InlineKeyboardBuilder()
            for h in target_houses:
                builder.button(text=f"🏢 {h.display_name}", callback_data=f"task_h_sel_{h.id}")
            builder.adjust(1)
            await callback.message.answer("কোন হাউজের সিম স্ট্যাটাস চেক করতে চান?", reply_markup=builder.as_markup())
    
    await callback.answer()

# --- ২. হাউজ সিলেক্ট করার হ্যান্ডেলার ---
@router.callback_query(F.data.startswith("task_h_sel_"))
async def handle_house_selection_for_task(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            return await callback.answer("❌ হাউজটি খুঁজে পাওয়া যায়নি।")

        await state.update_data(selected_house_id=house.id)
        await callback.message.edit_text(
            f"🏢 হাউজ: **{house.name}**\n\nসিম সিরিয়াল অথবা রেঞ্জ (Start-End) লিখে পাঠান:",
            parse_mode="Markdown"
        )
        await state.set_state(SIMStatusForm.serials)
    
    await callback.answer()

# --- ৩. সিরিয়াল ইনপুট প্রসেসিং এবং অটোমেশন কল ---
@router.message(SIMStatusForm.serials, flags={"permission": "sim_status_check"})
async def process_sim_serials(message: Message, state: FSMContext):
    # ১. ভ্যালিডেশন এবং এক্সপান্ড কল করা
    serials, invalid_lines, error_msg = validate_and_expand_serials(message.text)
    
    if error_msg:
        return await message.answer(error_msg, parse_mode="Markdown")

    # ২. ইউজারকে প্রসেসিং মেসেজ দেওয়া
    processing_msg = await message.answer(
        f"⏳ **প্রসেসিং শুরু হয়েছে...**\n🔍 মোট {bn_num(len(serials))}টি সিম চেক করা হচ্ছে।",
        parse_mode="Markdown"
    )

    try:
        # ৩. স্টেট থেকে হাউজ আইডি নিয়ে ক্রেডেনশিয়াল সংগ্রহ করা (হেল্পার ব্যবহার করে) ✅
        data = await state.get_data()
        house_id = data.get("selected_house_id")

        if not house_id:
            return await processing_msg.edit_text("❌ হাউজ আইডি পাওয়া যায়নি। পুনরায় চেষ্টা করুন।")

        credentials, error = await get_dms_credentials(house_id)
        
        if error:
            return await processing_msg.edit_text(error)

        # ৪. প্লে-রাইট অটোমেশন কল করা
        automation_result = await run_sim_status_check(serials, credentials)

        # ৫. প্রসেসিং মেসেজ ডিলিট করা
        try:
            await processing_msg.delete()
        except:
            pass

        # ৬. রেজাল্ট পাঠানো (টেলিগ্রাম লিমিট হ্যান্ডেল করে)
        if len(automation_result) > 4000:
            for i in range(0, len(automation_result), 4000):
                await message.answer(automation_result[i:i+4000])
        else:
            await message.answer(f"📊 **সার্চ রেজাল্ট:**\n\n{automation_result}")

    except Exception as e:
        error_text = str(e).replace("_", " ") 
        await message.answer(f"❌ এরর হয়েছে: {error_text}")
        
    finally:
        # FSM স্টেট ক্লিয়ার করা
        await state.clear()