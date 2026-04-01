import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.Services.Automation.Tasks.sim_status import run_sim_status_check
from app.Utils.validators import validate_and_expand_serials
from app.Utils.helpers import get_dms_credentials # নতুন ইম্পোর্ট ✅

router = Router()

class SIMStatusForm(StatesGroup):
    serials = State()

@router.callback_query(F.data == "run_sim_status", flags={"permission": "sim_status_check"})
async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔍 **সিম স্ট্যাটাস চেক**\n\nসিম সিরিয়ালগুলো (প্রতি লাইনে একটি) লিখে পাঠান:",
        parse_mode="Markdown"
    )
    await state.set_state(SIMStatusForm.serials)
    await callback.answer()

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
        # ৩. ডাটাবেজ কোয়েরির বদলে হেল্পার ফাংশন ব্যবহার (এক লাইনে কাজ শেষ) ✅
        credentials, error = await get_dms_credentials(message.from_user.id)
        
        if error:
            # যদি কোনো এরর থাকে (হাউজ যুক্ত নেই বা ক্রেডেনশিয়াল নেই)
            return await processing_msg.edit_text(error)

        # ৪. প্লে-রাইট অটোমেশন কল করা
        automation_result = await run_sim_status_check(serials, credentials)

        # ৫. প্রসেসিং মেসেজ ডিলিট করা
        try:
            await processing_msg.delete()
        except:
            pass

        # ৬. রেজাল্ট পাঠানো
        if len(automation_result) > 4000:
            for i in range(0, len(automation_result), 4000):
                await message.answer(automation_result[i:i+4000])
        else:
            await message.answer(f"📊 **সার্চ রেজাল্ট:**\n\n{automation_result}")

    except Exception as e:
        error_text = str(e).replace("_", " ") 
        await message.answer(f"❌ এরর হয়েছে: {error_text}")
        
    finally:
        await state.clear()



# import asyncio
# from aiogram import Router, F
# from aiogram.types import Message, CallbackQuery
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State, StatesGroup
# from sqlalchemy import select
# from sqlalchemy.orm import selectinload

# from app.Models.user import User
# from app.Services.Automation.Tasks.sim_status import run_sim_status_check
# from app.Services.db_service import async_session
# from app.Utils.validators import validate_and_expand_serials

# router = Router()

# # এই টাস্কের নিজস্ব স্টেট (এই ফাইলের ভেতরেই থাকবে)
# class SIMStatusForm(StatesGroup):
#     serials = State()

# # --- ইনলাইন বাটন থেকে টাস্ক শুরু ---
# @router.callback_query(F.data == "run_sim_status", flags={"permission": "sim_status_check"})
# async def trigger_sim_status(callback: CallbackQuery, state: FSMContext):
#     await callback.message.answer(
#         "🔍 **সিম স্ট্যাটাস চেক**\n\nসিম সিরিয়ালগুলো (প্রতি লাইনে একটি) লিখে পাঠান:",
#         parse_mode="Markdown"
#     )
#     await state.set_state(SIMStatusForm.serials)
#     await callback.answer()

# # --- সিরিয়াল ইনপুট প্রসেসিং এবং অটোমেশন কল ---
# @router.message(SIMStatusForm.serials, flags={"permission": "sim_status_check"})
# async def process_sim_serials(message: Message, state: FSMContext):
#     # ১. ভ্যালিডেশন এবং এক্সপান্ড কল করা (এটি সিরিয়াল লিস্টও রিটার্ন করে)
#     serials, invalid_lines, error_msg = validate_and_expand_serials(message.text)
    
#     # যদি ফরম্যাট ভুল হয় বা লিমিট ক্রস করে
#     if error_msg:
#         return await message.answer(error_msg, parse_mode="Markdown")

#     # ২. ইউজারকে একবারই প্রসেসিং মেসেজ দেওয়া
#     processing_msg = await message.answer(
#         f"⏳ **প্রসেসিং শুরু হয়েছে...**\n🔍 মোট {len(serials)}টি সিম চেক করা হচ্ছে।",
#         parse_mode="Markdown"
#     )

#     try:
#         async with async_session() as session:
#             # ৩. হাউজের DMS তথ্য ডাটাবেজ থেকে লোড করা
#             result = await session.execute(
#                 select(User).options(selectinload(User.house)).where(User.telegram_id == message.from_user.id)
#             )
#             user = result.scalar_one_or_none()
            
#             if not user or not user.house:
#                 return await processing_msg.edit_text("❌ আপনার সাথে কোনো হাউজ যুক্ত নেই।")

#             house = user.house
            
#             # DMS তথ্য চেক করা
#             if not all([house.dms_user, house.dms_pass, house.dms_house_id]):
#                 return await processing_msg.edit_text(f"❌ হাউজ '{house.name}' এর জন্য DMS Credentials সেট করা নেই।")

#             # অটোমেশনের জন্য ক্রেডেনশিয়াল ডিকশনারি
#             credentials = {
#                 "user": house.dms_user,
#                 "pass": house.dms_pass,
#                 "house_id": house.dms_house_id,
#                 "house_name": house.name
#             }

#         # ৪. প্লে-রাইট অটোমেশন কল করা
#         automation_result = await run_sim_status_check(serials, credentials)

#         # ৫. প্রসেসিং মেসেজ ডিলিট করা
#         try:
#             await processing_msg.delete()
#         except:
#             pass

#         # ৬. রেজাল্ট পাঠানো (টেলিগ্রাম লিমিট হ্যান্ডেল করে)
#         if len(automation_result) > 4000:
#             for i in range(0, len(automation_result), 4000):
#                 await message.answer(automation_result[i:i+4000])
#         else:
#             await message.answer(f"📊 **সার্চ রেজাল্ট:**\n\n{automation_result}")

#     except Exception as e:
#         error_text = str(e).replace("_", " ") 
#         await message.answer(f"❌ এরর হয়েছে: {error_text}")
        
#     finally:
#         # FSM স্টেট ক্লিয়ার করা
#         await state.clear()