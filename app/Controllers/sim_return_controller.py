from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# প্রয়োজনীয় সার্ভিস ও ইউটিলস ইম্পোর্ট
from app.Services.Automation.Tasks.sim_return import run_sim_return_task
from app.Utils.validators import validate_and_expand_serials
from app.Utils.helpers import get_dms_credentials

router = Router()

# এই টাস্কের নিজস্ব স্টেট (এই ফাইলের ভেতরেই ডিফাইন করা হয়েছে)
class SIMReturnForm(StatesGroup):
    serials = State()

# --- ১. ইনলাইন বাটন থেকে টাস্ক শুরু করা (Trigger) ---
@router.callback_query(F.data == "run_sim_return", flags={"permission": "task_sim_return"})
async def trigger_sim_return(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📥 **সিম রিটার্ন (SIM Return)**\n\nসিম সিরিয়াল অথবা রেঞ্জ (Start-End) লিখে পাঠান:",
        parse_mode="Markdown"
    )
    await state.set_state(SIMReturnForm.serials)
    await callback.answer()

# --- ২. সিরিয়াল ইনপুট প্রসেসিং এবং অটোমেশন রান ---
@router.message(SIMReturnForm.serials, flags={"permission": "task_sim_return"})
async def process_sim_return_serials(message: Message, state: FSMContext, bot):
    # ১. ভ্যালিডেশন এবং রেঞ্জ এক্সপান্ড (এক লাইনে সব কাজ শেষ)
    serials, invalid_lines, error_msg = validate_and_expand_serials(message.text)
    
    # ফরম্যাট ভুল হলে বা লিমিট ক্রস করলে মেসেজ দিবে
    if error_msg:
        return await message.answer(error_msg, parse_mode="Markdown")

    # ২. ইউজারের হাউজ ক্রেডেনশিয়াল সংগ্রহ করা (হেল্পার ফাংশন ব্যবহার করে)
    credentials, error = await get_dms_credentials(message.from_user.id)
    if error:
        return await message.answer(error)

    # ৩. ইউজারকে ওয়েটিং মেসেজ দেওয়া
    wait_msg = await message.answer(
        f"⏳ **সিম রিটার্ন প্রসেস শুরু হয়েছে...**\n"
        f"🔍 মোট {len(serials)}টি সিম এনালাইসিস করা হচ্ছে।\n"
        f"🤖 ওটিপি সংগ্রহ ও লগইন সম্পন্ন হতে ১-২ মিনিট সময় লাগতে পারে।",
        parse_mode="Markdown"
    )

    try:
        # ৪. প্লে-রাইট অটোমেশন টাস্ক কল করা
        automation_result = await run_sim_return_task(serials, credentials, bot, message.chat.id)
        
        # প্রসেসিং মেসেজ ডিলিট করে ফাইনাল রেজাল্ট পাঠানো
        await wait_msg.delete()
        await message.answer(automation_result, parse_mode="Markdown")

    except Exception as e:
        # এরর হ্যান্ডলিং (আন্ডারস্কোর রিমুভ করে সুন্দরভাবে দেখানো)
        error_text = str(e).replace("_", " ") 
        await wait_msg.edit_text(f"❌ এরর হয়েছে: {error_text}")
    
    finally:
        # FSM স্টেট ক্লিয়ার করা
        await state.clear()