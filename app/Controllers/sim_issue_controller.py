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
    serials = State()
    house_selection = State()
    retailer_code = State()

@router.callback_query(F.data == "run_sim_issue", flags={"permission": "sim_issue"})
async def trigger_sim_issue(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("📤 **সিম ইস্যু (Issue SIM)**\nসিম সিরিয়াল অথবা রেঞ্জ লিখে পাঠান:")
    await state.set_state(SIMIssueForm.serials)
    await callback.answer()

@router.message(SIMIssueForm.serials, flags={"permission": "sim_issue"})
async def process_issue_serials(message: Message, state: FSMContext):
    serials, invalid, error_msg = validate_and_expand_serials(message.text)
    if error_msg: return await message.answer(error_msg, parse_mode="Markdown")

    await state.update_data(temp_serials=serials)

    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.houses: return await message.answer("❌ হাউজ যুক্ত নেই।")

        if len(user.houses) == 1:
            house = user.houses[0]
            credentials = {"user": house.dms_user, "pass": house.dms_pass, "house_id": house.dms_house_id, "house_name": house.name, "code": house.code}
            return await start_issue_analysis(message, state, credentials, serials)

        builder = InlineKeyboardBuilder()
        for h in user.houses: builder.button(text=f"🏢 {h.name}", callback_data=f"issue_hsel_{h.id}")
        builder.adjust(1)
        await message.answer("কোন হাউজে সিম ইস্যু করতে চান?", reply_markup=builder.as_markup())
        await state.set_state(SIMIssueForm.house_selection)

@router.callback_query(F.data.startswith("issue_hsel_"), SIMIssueForm.house_selection)
async def handle_issue_house_choice(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    async with async_session() as session:
        house = await session.get(House, house_id)
        credentials = {"user": house.dms_user, "pass": house.dms_pass, "house_id": house.dms_house_id, "house_name": house.name, "code": house.code}
    
    await callback.message.delete()
    await start_issue_analysis(callback.message, state, credentials, data.get("temp_serials"))

async def start_issue_analysis(message: Message, state: FSMContext, credentials: dict, serials: list):
    wait_msg = await message.answer("⏳ সিম স্ট্যাটাস যাচাই করা হচ্ছে...")
    scanned_data, error = await run_sim_issue_status(serials, credentials)
    
    if error: return await wait_msg.edit_text(error)

    report_text, ready_list = process_issue_summary(scanned_data, credentials['house_name'])

    await wait_msg.delete()

    if not ready_list:
        return await message.answer(report_text + "\n\n⚠️ কোনো ইস্যুযোগ্য সিম পাওয়া যায়নি।")
    
    # ডাটা সেভ করে রিটেইলার কোড চাওয়া
    await state.update_data(ready_serials=ready_list, credentials=credentials)

    final_msg = report_text + f"\n\n👉 মোট {bn_num(len(ready_list))}টি সিম ইস্যু করা যাবে।\n**রিটেইলার কোড (উদা: R12345) লিখে পাঠান:**"
    await message.answer(final_msg, parse_mode="Markdown")
    await state.set_state(SIMIssueForm.retailer_code)


@router.message(SIMIssueForm.retailer_code, flags={"permission": "sim_issue"})
async def process_final_issue(message: Message, state: FSMContext):
    retailer_code = message.text.strip().upper()
    data = await state.get_data()
    
    wait_msg = await message.answer(f"⏳ `{retailer_code}` কোডে সিম ইস্যু করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।")
    result = await run_finalize_issue(data['ready_serials'], retailer_code, data['credentials'])
    
    await wait_msg.delete()
    await message.answer(result, parse_mode="Markdown")
    await state.clear()