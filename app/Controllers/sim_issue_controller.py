from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Models.house import House
from app.Services.Automation.Tasks.sim_issue import run_sim_issue_status, run_finalize_issue, process_issue_summary
from app.Utils.validators import validate_and_expand_serials
from app.Utils.helpers import bn_num
from app.Services.db_service import async_session

router = Router()

class SIMIssueForm(StatesGroup):
    house_selection = State() # প্রথমে হাউজ সিলেকশন
    serials = State()         # তারপর সিরিয়াল ইনপুট
    retailer_code = State()   # সবশেষে রিটেইলার কোড

# --- ১. টাস্ক শুরু এবং হাউজ চেক (Trigger) ---
@router.callback_query(F.data == "run_sim_issue", flags={"permission": "sim_issue"})
async def trigger_sim_issue(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_tg_id = callback.from_user.id
    
    # সুপার এডমিন চেক লজিক ✅
    from config.settings import SUPER_ADMIN_ID
    is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

    async with async_session() as session:
        target_houses = []

        if is_super_admin:
            # সুপার এডমিন হলে ডাটাবেজে থাকা সব হাউজ লোড করবে ✅
            res = await session.execute(select(House))
            target_houses = res.scalars().all()
        else:
            # সাধারণ ইউজার হলে শুধু তার সাথে লিঙ্ক করা হাউজগুলো নিবে
            res = await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )
            user = res.scalar_one_or_none()
            if user:
                target_houses = user.houses

        # হাউজ চেক
        if not target_houses:
            return await callback.message.answer("❌ বর্তমানে সিস্টেমে কোনো হাউজ নেই অথবা আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।")

        # ক. যদি শুধুমাত্র ১টি হাউজ থাকে
        if len(target_houses) == 1:
            house = target_houses[0]
            credentials = {
                "user": house.dms_user, "pass": house.dms_pass,
                "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
            }
            await state.update_data(credentials=credentials)
            await callback.message.answer(f"📤 **সিম ইস্যু ({house.name})**\n\nসিম সিরিয়াল অথবা রেঞ্জ লিখে পাঠান:")
            await state.set_state(SIMIssueForm.serials)
        
        # খ. যদি একাধিক হাউজ থাকে ✅
        else:
            builder = InlineKeyboardBuilder()
            for h in target_houses:
                builder.button(text=f"🏢 {h.display_name}", callback_data=f"issue_hsel_{h.id}")
            builder.adjust(1)
            await callback.message.answer("কোন হাউজে সিম ইস্যু করতে চান? আগে হাউজ সিলেক্ট করুন:", reply_markup=builder.as_markup())
            await state.set_state(SIMIssueForm.house_selection)
            
    await callback.answer()

# --- ২. একাধিক হাউজ থাকলে হাউজ সিলেকশন হ্যান্ডেলার ---
@router.callback_query(F.data.startswith("issue_hsel_"), SIMIssueForm.house_selection)
async def handle_issue_house_choice(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        house = await session.get(House, house_id)
        credentials = {
            "user": house.dms_user, "pass": house.dms_pass,
            "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
        }
        await state.update_data(credentials=credentials)
    
    await callback.message.edit_text(f"🏢 হাউজ: **{house.name}** সিলেক্ট করা হয়েছে।\n\nএখন সিম সিরিয়াল অথবা রেঞ্জ লিখে পাঠান:", parse_mode="Markdown")
    await state.set_state(SIMIssueForm.serials)
    await callback.answer()

# --- ৩. সিরিয়াল ইনপুট এবং এনালাইসিস ---
@router.message(SIMIssueForm.serials, flags={"permission": "sim_issue"})
async def process_issue_serials(message: Message, state: FSMContext):
    # সিরিয়াল ভ্যালিডেশন
    serials, invalid, error_msg = validate_and_expand_serials(message.text)
    if error_msg: return await message.answer(error_msg, parse_mode="Markdown")

    data = await state.get_data()
    credentials = data.get("credentials")

    wait_msg = await message.answer(f"⏳ **{credentials['house_name']}** এর সিম স্ট্যাটাস যাচাই করা হচ্ছে...")
    
    try:
        scanned_data, error = await run_sim_issue_status(serials, credentials)
        if error: return await wait_msg.edit_text(error)

        report_text, ready_list = process_issue_summary(scanned_data, credentials)

        await wait_msg.delete()

        if not ready_list:
            await state.clear()
            return await message.answer(report_text + "\n\n⚠️ কোনো ইস্যুযোগ্য সিম পাওয়া যায়নি।")
        
        # পরবর্তী ধাপের জন্য ডাটা সেভ
        await state.update_data(ready_serials=ready_list)

        final_msg = report_text + f"\n\n👉 মোট {bn_num(len(ready_list))}টি সিম ইস্যু করা যাবে।\n**রিটেইলার কোড (উদা: R12345) লিখে পাঠান:**"
        await message.answer(final_msg, parse_mode="Markdown")
        await state.set_state(SIMIssueForm.retailer_code)

    except Exception as e:
        await wait_msg.edit_text(f"❌ এরর: {str(e)}")

# --- ৪. চূড়ান্ত সাবমিশন ---
@router.message(SIMIssueForm.retailer_code, flags={"permission": "sim_issue"})
async def process_final_issue(message: Message, state: FSMContext):
    retailer_code = message.text.strip().upper()
    data = await state.get_data()
    
    wait_msg = await message.answer(f"⏳ `{retailer_code}` কোডে সিম ইস্যু করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।")
    
    try:
        result = await run_finalize_issue(data['ready_serials'], retailer_code, data['credentials'])
        await wait_msg.delete()
        await message.answer(result, parse_mode="Markdown")
    except Exception as e:
        await wait_msg.edit_text(f"❌ সাবমিশন এরর: {str(e)}")
    finally:
        await state.clear()