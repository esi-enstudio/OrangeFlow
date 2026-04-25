from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Models.house import House
from app.Services.Automation.Tasks.sim_return import run_sim_return_task
from app.Utils.validators import validate_and_expand_serials
from app.Services.db_service import async_session

router = Router()

class SIMReturnForm(StatesGroup):
    house_selection = State() # আগে হাউজ সিলেক্ট করবে
    serials = State()         # তারপর সিরিয়াল দিবে

# --- ১. ইনলাইন বাটন থেকে টাস্ক শুরু (হাউজ চেক) ---
@router.callback_query(F.data == "run_sim_return", flags={"permission": "sim_return"})
async def trigger_sim_return(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_tg_id = callback.from_user.id
    
    # সুপার এডমিন চেক ✅
    from config.settings import SUPER_ADMIN_ID
    is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

    async with async_session() as session:
        target_houses = []

        if is_super_admin:
            # সুপার এডমিন হলে ডাটাবেজে থাকা সব হাউজ লোড করবে ✅
            res = await session.execute(select(House))
            target_houses = res.scalars().all()
        else:
            # সাধারণ ইউজার হলে শুধু তার প্রোফাইলের হাউজগুলো নিবে
            result = await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )
            user = result.scalar_one_or_none()
            if user:
                target_houses = user.houses

        if not target_houses:
            return await callback.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।", show_alert=True)

        # কেস ১: যদি শুধুমাত্র ১টি হাউজ থাকে
        if len(target_houses) == 1:
            house = target_houses[0]
            await state.update_data(selected_house_id=house.id)
            # এখানেও h.display_name ব্যবহার করা হয়েছে ✅
            await callback.message.answer(
                f"🏢 হাউজ: **{house.display_name}**\n📥 সিম রিটার্ন করার জন্য সিরিয়াল অথবা রেঞ্জ লিখে পাঠান:",
                parse_mode="HTML"
            )
            await state.set_state(SIMReturnForm.serials)
        
        # কেস ২: যদি একাধিক হাউজ থাকে
        else:
            builder = InlineKeyboardBuilder()
            for h in target_houses:
                # গ্লোবাল নেম ফরম্যাট: Name (Suffix) ✅
                builder.button(text=f"🏢 {h.display_name}", callback_data=f"return_hsel_{h.id}")
            builder.adjust(1)
            
            await callback.message.answer(
                "কোন হাউজে সিম রিটার্ন করতে চান? হাউজ নির্বাচন করুন:", 
                reply_markup=builder.as_markup()
            )
            await state.set_state(SIMReturnForm.house_selection)
    
    await callback.answer()

# --- ২. হাউজ সিলেকশন হ্যান্ডেলার (একাধিক হাউজের জন্য) ---
@router.callback_query(F.data.startswith("return_hsel_"), SIMReturnForm.house_selection)
async def handle_return_house_choice(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            return await callback.answer("❌ হাউজটি পাওয়া যায়নি।", show_alert=True)
            
        await state.update_data(selected_house_id=house.id)
        await callback.message.edit_text(
            f"✅ নির্বাচিত হাউজ: **{house.name}**\n📥 এখন রিটার্ন করার জন্য সিরিয়াল অথবা রেঞ্জ লিখে পাঠান:",
            parse_mode="HTML"
        )
    
    await state.set_state(SIMReturnForm.serials)
    await callback.answer()

# --- ৩. সিরিয়াল ইনপুট প্রসেসিং এবং অটোমেশন কল ---
@router.message(SIMReturnForm.serials)
async def process_sim_return_serials(message: Message, state: FSMContext):
    # সিরিয়াল ভ্যালিডেশন
    serials, invalid, error_msg = validate_and_expand_serials(message.text)
    if error_msg:
        return await message.answer(error_msg, parse_mode="HTML")

    # স্টেট থেকে আগে সিলেক্ট করা হাউজ আইডি নেওয়া
    data = await state.get_data()
    house_id = data.get("selected_house_id")

    async with async_session() as session:
        house = await session.get(House, house_id)
        credentials = {
            "user": house.dms_user, "pass": house.dms_pass,
            "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
        }

    # অটোমেশন রান করা
    await execute_sim_return_automation(message, state, credentials, serials)

# --- ৪. অটোমেশন রান করার হেল্পার ফাংশন ---
async def execute_sim_return_automation(message: Message, state: FSMContext, credentials: dict, serials: list):
    current_bot = message.bot
    
    wait_msg = await message.answer(
        f"⏳ **রিটার্ন প্রসেস শুরু হয়েছে...**\n"
        f"🏢 হাউজ: {credentials['house_name']}\n",
        parse_mode="HTML"
    )

    try:
        # প্লে-রাইট অটোমেশন টাস্ক কল করা
        automation_result = await run_sim_return_task(serials, credentials, current_bot, message.chat.id)
        
        await wait_msg.delete()
        await message.answer(automation_result, parse_mode="HTML")

    except Exception as e:
        error_text = str(e).replace("_", " ") 
        await wait_msg.edit_text(f"❌ এরর হয়েছে: {error_text}")
    
    finally:
        await state.clear()