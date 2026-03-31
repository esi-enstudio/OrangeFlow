import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Services.Automation.Tasks.sim_status import run_sim_status_check
from app.Services.db_service import async_session

router = Router()

# এই টাস্কের নিজস্ব স্টেট (এই ফাইলের ভেতরেই থাকবে)
class SIMStatusForm(StatesGroup):
    serials = State()

# --- ১. ইনলাইন বাটন থেকে টাস্ক শুরু ---
@router.callback_query(F.data == "run_sim_status", flags={"permission": "task_sim_status"})
async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔍 **সিম স্ট্যাটাস চেক**\n\nসিম সিরিয়ালগুলো (প্রতি লাইনে একটি) লিখে পাঠান:",
        parse_mode="Markdown"
    )
    await state.set_state(SIMStatusForm.serials)
    await callback.answer()

# --- ২. সিরিয়াল ইনপুট প্রসেসিং এবং অটোমেশন কল ---
@router.message(SIMStatusForm.serials, flags={"permission": "task_sim_status"})
async def process_sim_serials(message: Message, state: FSMContext):
    serials_text = message.text.strip()
    if not serials_text:
        return await message.answer("⚠️ অনুগ্রহ করে অন্তত একটি সিম সিরিয়াল লিখে পাঠান।")
    
    serials = [s.strip() for s in serials_text.split("\n") if s.strip()]
    
    processing_msg = await message.answer(
        f"⏳ **প্রসেসিং শুরু হয়েছে...**\n🔍 মোট {len(serials)}টি সিরিয়াল চেক করা হচ্ছে।",
        parse_mode="Markdown"
    )

    try:
        async with async_session() as session:
            # হাউজের সকল DMS তথ্য লোড করা
            result = await session.execute(
                select(User).options(selectinload(User.house)).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            
            if not user or not user.house:
                return await processing_msg.edit_text("❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।")

            house = user.house

            # --- ডিবাগ প্রিন্ট (টার্মিনালে দেখবেন) ---
            print(f"DEBUG: Data fetched from DB:")
            print(f" - House Name: {house.name}")
            print(f" - DMS User: {house.dms_user}")
            print(f" - DMS Pass: {'****' if house.dms_pass else 'Empty'}")
            print(f" - DMS House ID: {house.dms_house_id}")


            
            # চেক করা হচ্ছে হাউজের DMS তথ্য আছে কি না
            if not house.dms_user or not house.dms_pass or not house.dms_house_id:
                return await processing_msg.edit_text("❌ এই হাউজের জন্য ডিএমএস ক্রেডেনশিয়াল (User, Pass, ID) সেট করা নেই। এডমিনকে দিয়ে সেট করান।")

            # অটোমেশনের জন্য ক্রেডেনশিয়াল ডিকশনারি
            credentials = {
                "user": house.dms_user,
                "pass": house.dms_pass,
                "house_id": house.dms_house_id,
                "house_name": house.name
            }

        # প্লে-রাইট অটোমেশন কল করা (এখন credentials পাস হচ্ছে)
        automation_result = await run_sim_status_check(serials, credentials)

        # মেসেজ এডিট না করে নতুন মেসেজ পাঠানো নিরাপদ (আইডি এরর এড়াতে)
        try:
            await processing_msg.delete()
        except:
            pass

        # Markdown এরর এড়াতে সিম্পল টেক্সট অথবা HTML ব্যবহার
        if len(automation_result) > 4000:
            for i in range(0, len(automation_result), 4000):
                await message.answer(automation_result[i:i+4000])
        else:
            await message.answer(f"📊 **সার্চ রেজাল্ট:**\n\n{automation_result}")

    except Exception as e:
        # এরর মেসেজটি স্ট্রিং হিসেবে পাঠানো
        error_text = str(e).replace("_", " ") # আন্ডারস্কোর Markdown ব্রেক করে
        await message.answer(f"❌ এরর হয়েছে: {error_text}")
        
    finally:
        await state.clear()