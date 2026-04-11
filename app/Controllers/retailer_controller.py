from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.Models.retailer import Retailer
from app.Models.user import User
from app.Services.db_service import async_session
from app.Services.Automation.Reports.retailer_excel import process_retailer_excel

router = Router()

class RetailerStates(StatesGroup):
    waiting_for_excel = State()
    manual_code = State()
    manual_name = State()

# --- ১. প্রধান মেনু ---
@router.message(F.text == "🏪 রিটেইলার ম্যানেজমেন্ট", flags={"permission": "manage_retailers"})
async def retailer_main_menu(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 রিটেইলার লিস্ট", callback_data="retailer_list_0")
    builder.button(text="📤 এক্সেল আপলোড (Bulk)", callback_data="retailer_upload")
    builder.button(text="🔍 সার্চ করুন", callback_data="retailer_search")
    builder.adjust(1)
    await message.answer("🏪 **রিটেইলার ম্যানেজমেন্ট**\nকি করতে চান নির্বাচন করুন:", reply_markup=builder.as_markup())

# --- ২. এক্সেল আপলোড হ্যান্ডেল ---
@router.callback_query(F.data == "retailer_upload")
async def start_upload(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 ডিএমএস থেকে ডাউনলোড করা **Retailer List** এক্সেল ফাইলটি পাঠান।")
    await state.set_state(RetailerStates.waiting_for_excel)
    await callback.answer()

@router.message(RetailerStates.waiting_for_excel, F.document)
async def handle_excel_upload(message: Message, state: FSMContext):
    # ইউজারের হাউজ বের করা (ধরি ইউজারের ১টি হাউজ আছে, না থাকলে সিলেকশন মেনু দিতে হবে)
    async with async_session() as session:
        user = (await session.execute(select(User).options(selectinload(User.houses)).where(User.telegram_id == message.from_user.id))).scalar_one()
        house_id = user.houses[0].id

    wait_msg = await message.answer("⏳ ফাইল প্রসেস হচ্ছে, এটি ৩০-৬০ সেকেন্ড সময় নিতে পারে...")
    
    file_path = f"temp_ret_{message.from_user.id}.xlsx"
    await message.bot.download(message.document, destination=file_path)
    
    count, err = await process_retailer_excel(file_path, house_id)
    
    if os.path.exists(file_path): os.remove(file_path)
    
    if err:
        await wait_msg.edit_text(f"❌ এরর: {err}")
    else:
        await wait_msg.edit_text(f"✅ সফল! {count}টি রিটেইলার ডাটাবেজে আপডেট করা হয়েছে।")
    await state.clear()

# --- ৩. রিটেইলার লিস্ট (Pagination) ---
@router.callback_query(F.data.startswith("retailer_list_"))
async def show_retailers(callback: CallbackQuery):
    offset = int(callback.data.split("_")[2])
    async with async_session() as session:
        # ডাটাবেজ থেকে রিটেইলার আনা
        res = await session.execute(select(Retailer).limit(10).offset(offset))
        retailers = res.scalars().all()
        
        if not retailers:
            return await callback.answer("আর কোনো রিটেইলার নেই।", show_alert=True)

        text = "📋 **রিটেইলার লিস্ট:**\n"
        builder = InlineKeyboardBuilder()
        for r in retailers:
            text += f"• {r.name} (`{r.code}`)\n"
        
        builder.button(text="⬅️", callback_data=f"retailer_list_{max(0, offset-10)}")
        builder.button(text="➡️", callback_data=f"retailer_list_{offset+10}")
        builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")