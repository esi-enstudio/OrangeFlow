import os
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.Models.retailer import Retailer
from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session
from app.Services.Automation.retailer_excel import process_retailer_excel
from app.Utils.helpers import bn_num, get_retailer_full_profile_text
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

class RetailerStates(StatesGroup):
    selected_house_id = State()
    waiting_for_excel = State()
    search_query = State()
    edit_value = State()

PAGE_LIMIT = 5

# --- ১. প্রোফাইল টেক্সট হেল্পার ---
def get_retailer_full_profile_text(r: Retailer):
    def clean(val): return str(val) if val and str(val).lower() != 'nan' else "N/A"

    # আরএসও-র নাম বের করা
    sr_name = r.field_force.name if r.field_force else "অ্যাসাইন করা নেই"
    
    return (
        f"🏪 **রিটেইলার বিস্তারিত প্রোফাইল**\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 প্রাথমিক পরিচয়:</b>\n🔹 নাম: {r.name}\n🔹 কোড: `{r.retailer_code}`\n🔹 টাইপ: {clean(r.type)}\n🔹 সচল: {clean(r.enabled)}\n\n"

        f"<b>📞 যোগাযোগ:</b>\n🔹 ফোন: {clean(r.contact_no)}\n🔹 iTop No: {clean(r.itop_number)}\n🔹 SR No: {clean(r.itop_sr_number)}\n\n"

        f"<b>📍 ঠিকানা:</b>\n🔹 থানা: {clean(r.thana)}\n🔹 রুট: {clean(r.route)}\n🔹 ঠিকানা: {clean(r.address)}\n\n"

        f"<b>👤 মালিক তথ্য:</b>\n🔹 মালিক: {clean(r.owner_name)}\n🔹 NID: {clean(r.nid)}\n━━━━━━━━━━━━━━━━━━━━"
    )

# --- ২. মেইন এন্ট্রি ---
@router.message(F.text == "🏪 রিটেইলারস", flags={"permission": "manage_retailer"})
async def retailer_main(event: types.Union[Message, CallbackQuery], state: FSMContext, permissions: list):
    user_id = event.from_user.id
    target = event if isinstance(event, Message) else event.message
    
    data = await state.get_data()
    selected_house_id = data.get('selected_house_id')

    async with async_session() as session:
        if selected_house_id:
            house = await session.get(House, selected_house_id)
            if house: return await show_house_retailer_menu(target, house.id, house.name, permissions)

        if int(user_id) == int(SUPER_ADMIN_ID):
            h_res = await session.execute(select(House))
            all_houses = h_res.scalars().all()
            builder = InlineKeyboardBuilder()
            for h in all_houses: builder.button(text=f"🏢 {h.display_name}", callback_data=f"ret_hsel_{h.id}")
            return await target.answer("🛠 হাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())

        res = await session.execute(select(User).options(selectinload(User.houses)).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        if not user or not user.houses: return await target.answer("❌ কোনো হাউজ যুক্ত নেই।")

        if len(user.houses) == 1:
            house = user.houses[0]
            await state.update_data(selected_house_id=house.id)
            return await show_house_retailer_menu(target, house.id, house.name, permissions)

        builder = InlineKeyboardBuilder()
        for h in user.houses: builder.button(text=f"🏢 {h.display_name}", callback_data=f"ret_hsel_{h.id}")
        await target.answer("🏢 হাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())

@router.callback_query(F.data == "ret_change_house")
async def handle_change_house(callback: CallbackQuery, state: FSMContext, permissions: list):
    await state.clear()
    await callback.message.delete()
    await retailer_main(callback, state, permissions)

@router.callback_query(F.data.startswith("ret_hsel_"))
async def handle_retailer_house_selection(callback: CallbackQuery, state: FSMContext, permissions: list):
    house_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        house = await session.get(House, house_id)
        await state.update_data(selected_house_id=house_id)
        await callback.message.delete()
        await show_house_retailer_menu(callback.message, house_id, house.name, permissions)

async def show_house_retailer_menu(message: Message, house_id: int, house_name: str, permissions: list):
    async with async_session() as session:
        count = await session.scalar(select(func.count(Retailer.id)).where(Retailer.house_id == house_id))
    builder = InlineKeyboardBuilder()
    if count > 0 and "view_retailer" in permissions:
        builder.button(text="📋 লিস্ট দেখুন", callback_data="ret_list_0")
        builder.button(text="🔍 সার্চ করুন", callback_data="ret_search_start")
    if "upload_retailer_excel" in permissions:
        builder.button(text="📤 এক্সেল আপলোড", callback_data="ret_upload_start")
        builder.button(text="📥 স্যাম্পল", callback_data="ret_sample_dl")
    builder.button(text="🔄 হাউজ পরিবর্তন", callback_data="ret_change_house")
    await message.answer(f"🏪 **রিটেইলার ম্যানেজমেন্ট**\n🏢 হাউজ: **{house_name}**\n📊 মোট: `{bn_num(count)}` জন", reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")

# --- ৩. লিস্ট এবং পেজিনেশন ---
@router.callback_query(F.data.startswith("ret_list_"), flags={"permission": "view_retailer"})
async def list_retailers(callback: CallbackQuery, state: FSMContext, permissions: list):
    offset = int(callback.data.split("_")[2])
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    if not house_id: return await callback.answer("❌ হাউজ সেশন আউট!", show_alert=True)

    async with async_session() as session:
        total = await session.scalar(select(func.count(Retailer.id)).where(Retailer.house_id == house_id))
        res = await session.execute(select(Retailer).where(Retailer.house_id == house_id).order_by(Retailer.name).limit(PAGE_LIMIT).offset(offset))
        retailers = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for r in retailers: builder.button(text=f"🏪 {r.name} ({r.itop_number or 'N/A'})", callback_data=f"ret_view_{r.id}")
        nav = []
        if offset > 0: nav.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"ret_list_{offset - PAGE_LIMIT}"))
        if offset + PAGE_LIMIT < total: nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"ret_list_{offset + PAGE_LIMIT}"))
        if nav: builder.row(*nav)
        builder.row(InlineKeyboardButton(text="🔙 মেনু", callback_data="ret_back_main"))
        await callback.message.edit_text(f"📋 **তালিকা** (মোট: {bn_num(total)}):", reply_markup=builder.adjust(1).as_markup())


# --- রিটেইলার বিস্তারিত প্রোফাইল (আপডেটেড) ✅ ---
@router.callback_query(F.data.startswith("ret_view_"), flags={"permission": "view_retailer"})
async def view_retailer_details(callback: CallbackQuery, permissions: list):
    # ১. কলব্যাক ডাটা থেকে আইডি নেওয়া
    ret_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        # ২. রিটেইলারের সাথে তার ফিল্ড ফোর্স (SR) তথ্য লোড করা
        res = await session.execute(
            select(Retailer)
            .options(selectinload(Retailer.field_force)) # রিলেশনশিপ লোড ✅
            .where(Retailer.id == ret_id)
        )
        r = res.scalar_one_or_none()
        
        if not r: 
            return await callback.answer("❌ রিটেইলার পাওয়া যায়নি।", show_alert=True)

        # ৩. হেল্পার ফাংশন থেকে প্রোফাইল টেক্সট জেনারেট করা
        profile_text = get_retailer_full_profile_text(r)
        
        # ৪. অ্যাকশন কিবোর্ড তৈরি
        builder = InlineKeyboardBuilder()
        
        # পারমিশন অনুযায়ী বাটন যোগ করা
        if "edit_retailer" in permissions:
            builder.button(text="✏️ তথ্য এডিট", callback_data=f"ret_edit_menu_{r.id}")
            
        if "delete_retailer" in permissions:
            builder.button(text="🗑 ডিলিট করুন", callback_data=f"ret_conf_del_{r.id}")
        
        # ডিফল্ট বাটন
        builder.button(text="🔙 লিস্টে ফিরুন", callback_data="ret_list_0")
        
        builder.adjust(2) # এক রো-তে ২ টি বাটন

        # ৫. মেসেজ আপডেট করা
        try:
            await callback.message.edit_text(
                profile_text, 
                reply_markup=builder.as_markup(), 
                parse_mode="HTML"
            )
        except Exception:
            # যদি মেসেজ এডিট করতে সমস্যা হয় (যেমন একই ডাটা), তবে নতুন মেসেজ দিবে
            await callback.message.answer(
                profile_text, 
                reply_markup=builder.as_markup(), 
                parse_mode="HTML"
            )
            
    await callback.answer()








@router.callback_query(F.data.startswith("ret_edit_menu_"), flags={"permission": "edit_retailer"})
async def show_retailer_edit_fields(callback: CallbackQuery):
    ret_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()
    # এখানে কলাম নামগুলো মডেলের সাথে ম্যাচ করানো হয়েছে ✅
    fields = [
        ("নাম", "name"), ("কোড", "retailer_code"), ("টাইপ", "type"), ("সচল", "enabled"),
        ("ফোন", "contact_no"), ("iTop", "itop_number"), ("থানা", "thana"), ("রুট", "route")
    ]
    for label, field in fields: builder.button(text=label, callback_data=f"retedit:{field}:{ret_id}")
    builder.button(text="🔙 প্রোফাইল", callback_data=f"ret_view_{ret_id}")
    await callback.message.edit_text("কোন তথ্যটি পরিবর্তন করবেন?", reply_markup=builder.adjust(2).as_markup())

@router.callback_query(F.data.startswith("retedit:"), flags={"permission": "edit_retailer"})
async def start_retailer_edit_input(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    field, ret_id = parts[1], int(parts[2])
    async with async_session() as session:
        r = await session.get(Retailer, ret_id)
        curr = getattr(r, field) or "খালি"
        await state.update_data(edit_ret_id=ret_id, edit_field=field)
        await callback.message.answer(f"📝 <b>{field.upper()}</b> পরিবর্তন\nবর্তমান: `{curr}`\n\nনতুন তথ্যটি লিখে পাঠান:", parse_mode="HTML")
        await state.set_state(RetailerStates.edit_value)

@router.message(RetailerStates.edit_value)
async def save_retailer_edit(message: Message, state: FSMContext, permissions: list):
    data = await state.get_data()
    async with async_session() as session:
        r = await session.get(Retailer, data['edit_ret_id'])
        setattr(r, data['edit_field'], message.text.strip())
        await session.commit()
        await session.refresh(r)
        await message.answer(f"✅ সফলভাবে আপডেট হয়েছে।")
        # সেশন আইডি রেখে বাকি এডিট ডাটা মুছা হয়েছে ✅
        await state.set_state(None) 
        await view_retailer_details_manual(message, r, permissions)

async def view_retailer_details_manual(message: Message, r: Retailer, permissions: list):
    builder = InlineKeyboardBuilder()
    if "edit_retailer" in permissions: builder.button(text="✏️ এডিট", callback_data=f"ret_edit_menu_{r.id}")
    builder.button(text="📋 লিস্ট", callback_data="ret_list_0")
    await message.answer(get_retailer_full_profile_text(r), reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")

# --- ৫. ফাইল আপলোড ---
@router.callback_query(F.data == "ret_upload_start")
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 রিটেইলার এক্সেল ফাইলটি পাঠান।")
    await state.set_state(RetailerStates.waiting_for_excel)

@router.message(RetailerStates.waiting_for_excel, F.document)
async def handle_retailer_file(message: Message, state: FSMContext):
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    if not house_id: return await message.answer("❌ সেশন আউট!")
    
    file_path = f"temp_ret_{message.from_user.id}.xlsx"
    wait_msg = await message.answer("⏳ ফাইলটি ডাউনলোড ও প্রসেসিং শুরু হচ্ছে...")

    try:
        await message.bot.download(message.document, destination=file_path)

        # লাইভ প্রগ্রেস আপডেট ফাংশন ✅
        async def update_telegram_progress(text):
            try: await wait_msg.edit_text(text, parse_mode="Markdown")
            except: pass

        # সার্ভিস কল (প্রগ্রেস কলব্যাক সহ) ✅
        count, err = await process_retailer_excel(file_path, house_id, update_telegram_progress)
        
        if err:
            await wait_msg.edit_text(f"❌ এরর: {err}")
        else:
            await wait_msg.edit_text(f"✅ সফল! এই হাউজের জন্য মোট `{bn_num(count)}`টি রিটেইলার আপডেট/লিঙ্ক করা হয়েছে।")
    
    except Exception as e:
        await wait_msg.edit_text(f"❌ এরর: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        await state.set_state(None)

# --- ৬. সার্চ এবং ডিলিট ---
@router.callback_query(F.data.startswith("ret_conf_del_"))
async def confirm_del(callback: CallbackQuery):
    ret_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ নিশ্চিত ডিলিট", callback_data=f"ret_fdel_{ret_id}")
    builder.button(text="❌ বাতিল", callback_data=f"ret_view_{ret_id}")
    await callback.message.edit_text("⚠️ নিশ্চিত ডিলিট করবেন?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("ret_fdel_"))
async def final_del(callback: CallbackQuery, state: FSMContext, permissions: list):
    ret_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        r = await session.get(Retailer, ret_id)
        if r: await session.delete(r); await session.commit()
    await callback.answer("🗑 মুছে ফেলা হয়েছে।")
    await list_retailers(callback, state, permissions) # state পাস করা হয়েছে ✅

@router.callback_query(F.data == "ret_back_main")
async def back_main(callback: CallbackQuery, state: FSMContext, permissions: list):
    await callback.message.delete()
    await retailer_main(callback, state, permissions)