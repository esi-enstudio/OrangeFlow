from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.Services.Automation.field_force_excel import process_field_force_excel
from app.Utils.helpers import get_dms_credentials

router = Router()

class FieldForceStates(StatesGroup):
    waiting_for_excel = State()

@router.message(F.text == "👥 ফিল্ড ফোর্স", flags={"permission": "manage_field_force"})
async def field_force_menu(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 লিস্ট দেখুন", callback_data="ff_list")
    builder.button(text="📤 এক্সেল আপলোড", callback_data="ff_upload")
    builder.button(text="➕ নতুন (Manual)", callback_data="ff_add_manual")
    builder.adjust(1)
    
    await message.answer("👥 **ফিল্ড ফোর্স ম্যানেজমেন্ট**\nনিচের অপশনগুলো বেছে নিন:", reply_markup=builder.as_markup())

# এক্সেল আপলোড ট্রিগার
@router.callback_query(F.data == "ff_upload")
async def trigger_upload(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 অনুগ্রহ করে ফিল্ড ফোর্স ডাটা সম্বলিত এক্সেল (.xlsx) ফাইলটি পাঠান।")
    await state.set_state(FieldForceStates.waiting_for_excel)
    await callback.answer()

# ফাইল রিসিভ হ্যান্ডেলার
@router.message(FieldForceStates.waiting_for_excel, F.content_type == ContentType.DOCUMENT)
async def handle_ff_file(message: Message, state: FSMContext):
    document = message.document
    if not document.file_name.endswith(('.xlsx', '.xls')):
        return await message.answer("❌ ভুল ফাইল ফরম্যাট! শুধু এক্সেল ফাইল পাঠান।")

    # ইউজারের হাউজ আইডি নেওয়া
    credentials, error = await get_dms_credentials(message.from_user.id)
    if error: return await message.answer(error)
    
    wait_msg = await message.answer("⏳ ফাইল প্রসেস করা হচ্ছে...")
    
    # ফাইল ডাউনলোড
    file_path = f"temp_{document.file_name}"
    await message.bot.download(document, destination=file_path)
    
    # ডাটাবেজ আপডেট
    count, err = await process_field_force_excel(file_path, credentials['house_id'])
    
    if os.path.exists(file_path): os.remove(file_path)
    
    if err:
        await wait_msg.edit_text(f"❌ এরর: {err}")
    else:
        await wait_msg.edit_text(f"✅ সফল! {count} জন ফিল্ড ফোর্স মেম্বার যুক্ত হয়েছে।")
    
    await state.clear()