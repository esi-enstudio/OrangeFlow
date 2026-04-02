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
from app.Utils.helpers import get_dms_credentials

router = Router()

# এই ফাইলের নিজস্ব স্টেট
class SIMStatusForm(StatesGroup):
    serials = State()

# --- ১. ইনলাইন বাটন থেকে টাস্ক শুরু (হাউজ সিলেকশন লজিকসহ) ---
@router.callback_query(F.data == "run_sim_status", flags={"permission": "sim_status_check"})
async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        # ইউজারের সাথে যুক্ত সব হাউজ লোড করা
        res = await session.execute(
            select(DBUser).options(selectinload(DBUser.houses)).where(DBUser.telegram_id == callback.from_user.id)
        )
        user = res.scalar_one_or_none()
        
        if not user or not user.houses:
            return await callback.answer("❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।", show_alert=True)

        # যদি হাউজ মাত্র ১টি হয় - সরাসরি সিরিয়াল চাবে
        if len(user.houses) == 1:
            house = user.houses[0]
            await state.update_data(selected_house_id=house.id)
            await callback.message.answer(
                f"🏢 হাউজ: **{house.name}**\n\nসিম সিরিয়াল অথবা রেঞ্জ (Start-End) লিখে পাঠান:",
                parse_mode="Markdown"
            )
            await state.set_state(SIMStatusForm.serials)
        
        # যদি একাধিক হাউজ থাকে - সিলেকশন মেনু দেখাবে
        else:
            builder = InlineKeyboardBuilder()
            for h in user.houses:
                builder.button(text=f"🏢 {h.name}", callback_data=f"task_h_sel_{h.id}")
            builder.adjust(2)
            await callback.message.answer("আপনি কোন হাউজের ডাটা চেক করতে চান?", reply_markup=builder.as_markup())
    
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
        f"⏳ **প্রসেসিং শুরু হয়েছে...**\n🔍 মোট {len(serials)}টি সিম চেক করা হচ্ছে।",
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




# class SIMStatusForm(StatesGroup):
#     serials = State()

# @router.callback_query(F.data == "run_sim_status", flags={"permission": "sim_status_check"})
# async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
#     async with async_session() as session:
#         res = await session.execute(
#             select(User).options(selectinload(User.houses)).where(User.telegram_id == callback.from_user.id)
#         )
#         user = res.scalar_one_or_none()
        
#         if not user or not user.houses:
#             return await callback.answer("❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।", show_alert=True)

        
#         # যদি ১টি হাউজ থাকে - সরাসরি প্রসেস
#         if len(user.houses) == 1:
#             house = user.houses[0]
#             await state.update_data(target_house_id=house.id)
#             await callback.message.answer(f"🏢 হাউজ: **{house.name}**\nসিরিয়ালগুলো লিখে পাঠান:")
#             await state.set_state(SIMStatusForm.serials)
        
#         # যদি একাধিক হাউজ থাকে - সিলেকশন মেনু
#         else:
#             builder = InlineKeyboardBuilder()
#             for h in user.houses:
#                 builder.button(text=f"🏢 {h.name}", callback_data=f"task_h_sel_{h.id}")
#             builder.adjust(2)
#             await callback.message.answer("আপনি কোন হাউজের ডাটা চেক করতে চান?", reply_markup=builder.as_markup())
    
#     await callback.answer()

# হাউজ সিলেক্ট করার হ্যান্ডেলার
# @router.callback_query(F.data.startswith("select_h_task_"))
# async def handle_house_selection_for_task(callback: CallbackQuery, state: FSMContext):
#     house_id = int(callback.data.split("_")[3])
#     async with async_session() as session:
#         house = await session.get(House, house_id)
#         await state.update_data(selected_house_id=house.id)
#         await callback.message.edit_text(f"🏢 হাউজ: **{house.name}**\n\nসিরিয়ালগুলো লিখে পাঠান:")
#         await state.set_state(SIMStatusForm.serials)
#     await callback.answer()

# @router.message(SIMStatusForm.serials, flags={"permission": "sim_status_check"})
# async def process_sim_serials(message: Message, state: FSMContext):
#     # ১. ভ্যালিডেশন এবং এক্সপান্ড কল করা
#     serials, invalid_lines, error_msg = validate_and_expand_serials(message.text)
    
#     if error_msg:
#         return await message.answer(error_msg, parse_mode="Markdown")

#     # ২. ইউজারকে প্রসেসিং মেসেজ দেওয়া
#     processing_msg = await message.answer(
#         f"⏳ **প্রসেসিং শুরু হয়েছে...**\n🔍 মোট {len(serials)}টি সিম চেক করা হচ্ছে।",
#         parse_mode="Markdown"
#     )

#     try:
#         # ৩. ডাটাবেজ কোয়েরির বদলে হেল্পার ফাংশন ব্যবহার (এক লাইনে কাজ শেষ) ✅
#         credentials, error = await get_dms_credentials(message.from_user.id)
        
#         if error:
#             # যদি কোনো এরর থাকে (হাউজ যুক্ত নেই বা ক্রেডেনশিয়াল নেই)
#             return await processing_msg.edit_text(error)

#         # ৪. প্লে-রাইট অটোমেশন কল করা
#         automation_result = await run_sim_status_check(serials, credentials)

#         # ৫. প্রসেসিং মেসেজ ডিলিট করা
#         try:
#             await processing_msg.delete()
#         except:
#             pass

#         # ৬. রেজাল্ট পাঠানো
#         if len(automation_result) > 4000:
#             for i in range(0, len(automation_result), 4000):
#                 await message.answer(automation_result[i:i+4000])
#         else:
#             await message.answer(f"📊 **সার্চ রেজাল্ট:**\n\n{automation_result}")

#     except Exception as e:
#         error_text = str(e).replace("_", " ") 
#         await message.answer(f"❌ এরর হয়েছে: {error_text}")
        
#     finally:
#         await state.clear()