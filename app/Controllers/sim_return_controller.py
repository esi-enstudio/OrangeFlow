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
    serials = State()
    house_selection = State() # একাধিক হাউজ থাকলে এটি ব্যবহৃত হবে

# --- ২. সিরিয়াল ইনপুট প্রসেসিং এবং হাউজ চেক ---
@router.message(SIMReturnForm.serials, flags={"permission": "sim_return"})
async def process_sim_return_serials(message: Message, state: FSMContext):
    # ১. সিরিয়াল ভ্যালিডেশন এবং রেঞ্জ এক্সপান্ড
    serials, invalid_lines, error_msg = validate_and_expand_serials(message.text)
    
    if error_msg:
        return await message.answer(error_msg, parse_mode="Markdown")

    # সিরিয়ালগুলো সাময়িকভাবে স্টেটে সেভ করে রাখা
    await state.update_data(temp_serials=serials)

    async with async_session() as session:
        # ২. ডাটাবেজ থেকে ইউজারের সাথে যুক্ত হাউজগুলো লোড করা
        result = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.houses:
            return await message.answer("❌ আপনার সাথে কোনো হাউজ যুক্ত নেই। এডমিনের সাথে যোগাযোগ করুন।")

        # ৩. যদি শুধুমাত্র ১টি হাউজ থাকে, সরাসরি প্রসেস শুরু করবে
        if len(user.houses) == 1:
            house = user.houses[0]
            credentials = {
                "user": house.dms_user, "pass": house.dms_pass,
                "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
            }
            return await execute_sim_return_automation(message, state, credentials, serials)

        # ৪. যদি একাধিক হাউজ থাকে, হাউজ সিলেক্ট করার বাটন দেখাবে
        builder = InlineKeyboardBuilder()
        for h in user.houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"return_hsel_{h.id}")
        builder.adjust(1)

        await message.answer(
            "আপনার সাথে একাধিক হাউজ যুক্ত রয়েছে। কোন হাউজে সিম রিটার্ন করতে চান?", 
            reply_markup=builder.as_markup()
        )
        await state.set_state(SIMReturnForm.house_selection)

# --- ৩. একাধিক হাউজ থাকলে বাটন ক্লিক হ্যান্ডেলার ---
@router.callback_query(F.data.startswith("return_hsel_"), SIMReturnForm.house_selection)
async def handle_return_house_choice(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    serials = data.get("temp_serials")

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            return await callback.answer("❌ হাউজটি পাওয়া যায়নি।", show_alert=True)
            
        credentials = {
            "user": house.dms_user, "pass": house.dms_pass,
            "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
        }
    
    await callback.message.delete() # বাটন মেসেজটি মুছে ফেলা
    await execute_sim_return_automation(callback.message, state, credentials, serials)
    await callback.answer()

# --- ৪. অটোমেশন রান করার হেল্পার ফাংশন (ডুপ্লিকেট কোড এড়াতে) ---
async def execute_sim_return_automation(message: Message, state: FSMContext, credentials: dict, serials: list):
    from main import bot # মেইন বট অবজেক্ট ইম্পোর্ট
    
    wait_msg = await message.answer(
        f"⏳ **রিটার্ন প্রসেস শুরু হয়েছে...**\n"
        f"🏢 হাউজ: {credentials['house_name']}\n"
        f"🤖 ওটিপি সংগ্রহ ও লগইন সম্পন্ন হতে ১-২ মিনিট সময় লাগতে পারে।",
        parse_mode="Markdown"
    )

    try:
        # প্লে-রাইট অটোমেশন টাস্ক কল করা
        automation_result = await run_sim_return_task(serials, credentials, bot, message.chat.id)
        
        await wait_msg.delete()
        await message.answer(automation_result, parse_mode="Markdown")

    except Exception as e:
        error_text = str(e).replace("_", " ") 
        await wait_msg.edit_text(f"❌ এরর হয়েছে: {error_text}")
    
    finally:
        await state.clear()