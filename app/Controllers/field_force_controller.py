import asyncio
import os
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.Models.field_force import FieldForce
from app.Models.user import User
from app.Models.house import House

from app.Services.db_service import async_session
from app.Services.Automation.field_force_excel import process_field_force_excel, generate_ff_sample, generate_ff_sample
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

from app.Views.keyboards.inline import (
    get_field_force_house_selection_kb,
    get_field_force_main_kb,
    get_ff_pagination_kb,
    get_ff_action_kb,
    get_ff_edit_categories_kb,
    get_ff_fields_by_category_kb
)

logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# FSM States
# ==========================================
class FFStates(StatesGroup):
    waiting_for_house = State()
    waiting_for_excel = State()
    searching = State()
    editing_value = State()

# ==========================================
# ১. মেইন এন্ট্রি (হাউজ চেক)
# ==========================================
@router.message(F.text == "👥 ফিল্ড ফোর্স", flags={"permission": "manage_field_force"})
async def field_force_start(message: Message, state: FSMContext):
    await state.clear()
    await handle_ff_house_logic(message, state, message.from_user.id)

# হাউজ পরিবর্তন বাটন হ্যান্ডেলার ফিক্স ✅
@router.callback_query(F.data == "ff_change_house")
async def change_house_ff(callback: CallbackQuery, state: FSMContext):
    # এখানে callback.from_user.id ব্যবহার করতে হবে
    await handle_ff_house_logic(callback.message, state, callback.from_user.id, is_callback=True)
    await callback.answer()

async def handle_ff_house_logic(message: Message, state: FSMContext, user_tg_id, is_callback=False):
    async with async_session() as session:
        # ১. চেক করা ইউজার কি সুপার এডমিন?
        is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))
        
        target_houses = []

        if is_super_admin:
            # সুপার এডমিন হলে ডাটাবেজের সব হাউজ লোড করবে ✅
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

        # ২. হাউজ চেক এবং রেসপন্স
        if not target_houses:
            msg_text = "❌ বর্তমানে সিস্টেমে কোনো হাউজ তৈরি করা নেই অথবা আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।"
            return await message.edit_text(msg_text) if is_callback else await message.answer(msg_text)

        # ৩. যদি মাত্র ১টি হাউজ থাকে (সরাসরি মেইন ড্যাশবোর্ড)
        if len(target_houses) == 1:
            await render_ff_main(message, target_houses[0].id, is_callback)
        else:
            # ৪. একাধিক হাউজ থাকলে সিলেকশন মেনু
            kb = get_field_force_house_selection_kb(target_houses)
            text = "🏢 **হাউজ নির্বাচন করুন:**"
            
            if is_callback:
                await message.edit_text(text, reply_markup=kb)
            else:
                await message.answer(text, reply_markup=kb)



# --- ২. স্যাম্পল ডাউনলোড ফিক্স (নামের অমিল ঠিক করা হয়েছে) ---
@router.callback_query(F.data == "ff_sample_dl")
async def download_sample(callback: CallbackQuery):
    # নিশ্চিত করুন app/Services/Automation/Reports/field_force_excel.py তে এই ফাংশনটি আছে
    file_path = "Field_Force_Sample.xlsx"
    try:
        await generate_ff_sample(file_path)
        await callback.message.answer_document(
            FSInputFile(file_path), 
            caption="📝 ফিল্ড ফোর্স স্যাম্পল ফাইল।\nএটি পূরণ করে '📤 এক্সেল আপলোড' বাটনে গিয়ে আপলোড করুন।"
        )
    except Exception as e:
        await callback.message.answer(f"❌ স্যাম্পল তৈরি করা যায়নি: {e}")
    
    if os.path.exists(file_path): os.remove(file_path)
    await callback.answer()



# হাউজ সিলেকশন হ্যান্ডেলার
@router.callback_query(F.data.startswith("ff_hsel_"))
async def handle_ff_house_selection(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[2])
    await callback.message.delete()
    await render_ff_main(callback.message, house_id)
    await callback.answer()

@router.callback_query(F.data == "ff_change_house")
async def change_house_ff(callback: CallbackQuery, state: FSMContext):
    await field_force_start(callback.message, state)
    await callback.answer()

# ==========================================
# ২. মডিউল ড্যাশবোর্ড (Render Logic)
# ==========================================
async def render_ff_main(message: Message, house_id: int, is_callback=False):
    user_tg_id = message.chat.id # ইউজারের টেলিগ্রাম আইডি
    
    async with async_session() as session:
        # ১. চেক করা ইউজার কি সুপার এডমিন কি না
        is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

        # ২. মেম্বার কাউন্ট এবং হাউজ ডাটা
        house = await session.get(House, house_id)
        total_count = await session.scalar(
            select(func.count(FieldForce.id)).where(FieldForce.house_id == house_id)
        )
        
        # ৩. এই ইউজারের সাথে কোন প্রোফাইল লিঙ্ক করা আছে কি না দেখা
        ff_res = await session.execute(
            select(FieldForce.id).where(FieldForce.user_id == (
                select(User.id).where(User.telegram_id == user_tg_id).scalar_subquery()
            ))
        )
        personal_ff_id = ff_res.scalar_one_or_none()

        # ৪. পারমিশন ম্যানেজমেন্ট ✅
        # মিডলওয়্যার থেকে প্রাপ্ত পারমিশন অথবা সুপার এডমিনের জন্য ফুল লিস্ট
        # এখানে 'permissions' লিস্টটি আপনার লজিক অনুযায়ী আসবে
        # সুপার এডমিন হলে আমরা তাকে ম্যানেজমেন্টের সব ক্ষমতা দিব
        kb_permissions = ["view_field_force", "create_field_force", "edit_field_force", "delete_field_force"]
        
        text = (
            f"🏪 **ফিল্ড ফোর্স ম্যানেজমেন্ট**\n"
            f"🏢 হাউজ: **{house.name}**\n\n"
            f"📊 এই হাউজে মোট **{bn_num(total_count)}** জন মেম্বার আছে।"
        )

        # ৫. কিবোর্ড কল করার সময় is_admin এবং permissions পাঠানো
        kb = get_field_force_main_kb(
            house_id=house_id, 
            total_count=total_count, 
            permissions=kb_permissions, 
            is_admin=is_super_admin, 
            personal_ff_id=personal_ff_id
        )

        if is_callback:
            await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("ff_back_main_"))
async def back_to_ff_main(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[3])
    await render_ff_main(callback.message, house_id)
    await callback.answer()

# ==========================================
# ৩. লিস্ট দেখা (Pagination)
# ==========================================
@router.callback_query(F.data.startswith("ff_list_"), flags={"permission": "view_field_force"})
async def handle_ff_list(callback: CallbackQuery):
    parts = callback.data.split("_")
    house_id = int(parts[2])
    page = int(parts[3])
    limit = 5
    offset = (page - 1) * limit

    async with async_session() as session:
        total = await session.scalar(select(func.count(FieldForce.id)).where(FieldForce.house_id == house_id))
        total_pages = (total + limit - 1) // limit
        
        res = await session.execute(
            select(FieldForce).where(FieldForce.house_id == house_id).offset(offset).limit(limit)
        )
        members = res.scalars().all()

        if not members:
            return await callback.answer("⚠️ কোনো মেম্বার পাওয়া যায়নি।", show_alert=True)

        text = f"📋 **মেম্বার তালিকা** (মোট: {bn_num(total)} জন):"
        kb = get_ff_pagination_kb(members, page, total_pages, house_id)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ==========================================
# ৪. প্রোফাইল ভিউ এবং স্ট্যাটাস টগল
# ==========================================
@router.callback_query(F.data.startswith("ff_view_"), flags={"permission": "view_field_force"})
async def view_ff_profile(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[2])
    user_tg_id = callback.from_user.id
    
    async with async_session() as session:
        # ১. ডাটাবেজ থেকে ফিল্ড ফোর্স মেম্বারের ডাটা নেওয়া
        m = await session.get(FieldForce, ff_id)
        if not m: 
            return await callback.answer("❌ মেম্বার পাওয়া যায়নি।", show_alert=True)

        # ২. সিকিউরিটি চেক: ইউজার কি সুপার এডমিন অথবা এই প্রোফাইলের মালিক? ✅
        is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))
        
        # ইউজারের ডাটাবেজ আইডি বের করা (মালিকানা চেক করার জন্য)
        db_user_id = await session.scalar(select(User.id).where(User.telegram_id == user_tg_id))
        
        if not is_super_admin and m.user_id != db_user_id:
            return await callback.answer("🚫 আপনি শুধুমাত্র নিজের প্রোফাইল দেখার অনুমতি রাখেন!", show_alert=True)

        # ৩. প্রোফাইল টেক্সট জেনারেট করা (Helper Function থেকে)
        from app.Utils.helpers import get_field_force_full_profile_text
        details = get_field_force_full_profile_text(m)
        
        # ৪. অ্যাকশন কিবোর্ড জেনারেট করা
        # এখানে আমরা চেক করছি—যদি সে মালিক হয় কিন্তু সুপার এডমিন না হয়, সে কি এডিট করতে পারবে?
        # আপাতত সুপার এডমিনকে সব পারমিশন দিচ্ছি, অন্যদের ক্ষেত্রে শুধু 'তথ্য এডিট' বাটন থাকবে
        
        # আপনার মিডলওয়্যার থেকে পাওয়া পারমিশন লিস্ট ব্যবহার করুন (যদি থাকে)
        # অথবা সিম্পল লজিক:
        perms = ["edit_field_force"] # সাধারণ ইউজারের জন্য ডিফল্ট
        if is_super_admin:
            perms.append("delete_field_force")
        
        kb = get_ff_action_kb(m.id, m.house_id, m.status, perms)
        
        # ৫. মেসেজ আপডেট করা
        try:
            await callback.message.edit_text(details, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            # যদি মেসেজ এডিট করতে সমস্যা হয় (যেমন: একই ডাটা), তবে নতুন মেসেজ পাঠাবে
            await callback.message.answer(details, reply_markup=kb, parse_mode="HTML")
            
    await callback.answer()


# --- এডিট ক্যাটাগরি সিলেকশন ---
@router.callback_query(F.data.startswith(("ff_edit_", "ff_ecat_")), flags={"permission": "edit_field_force"})
async def show_edit_categories(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    ff_id = int(data_parts[-1]) 

    if "ff_ecat_" in callback.data:
        # এটি ক্যাটাগরির ভেতরে ঢুকেছে (Format: ff_ecat_{key}_{id})
        category_key = data_parts[2] # basic, bank, personal etc.
        await callback.message.edit_text(
            "কোন তথ্যটি আপডেট করতে চান?", 
            reply_markup=get_ff_fields_by_category_kb(category_key, ff_id)
        )
    else:
        # এটি মেইন এডিট মেনু (Format: ff_edit_{id})
        await callback.message.edit_text(
            "কোন ধরণের তথ্য এডিট করতে চান?", 
            reply_markup=get_ff_edit_categories_kb(ff_id)
        )
    await callback.answer()



@router.callback_query(F.data.startswith("ff_toggle_"), flags={"permission": "edit_field_force"})
async def toggle_ff_status(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        m = await session.get(FieldForce, ff_id)
        m.status = "Inactive" if m.status == "Active" else "Active"
        await session.commit()
        await callback.answer(f"স্ট্যাটাস {m.status} করা হয়েছে।")
    await view_ff_profile(callback)

# ==========================================
# ৫. তথ্য আপডেট (Edit Logic)
# ==========================================
@router.callback_query(F.data.startswith("ff_edit_"), flags={"permission": "edit_field_force"})
async def start_ff_edit(callback: CallbackQuery):
    # ডাটা পার্টস আলাদা করা
    data_parts = callback.data.split("_")
    
    # যদি এটি ক্যাটাগরি সিলেকশন না হয় (শুধু ff_edit_ID হয়)
    if "cat_" not in callback.data:
        ff_id = int(data_parts[2])
        # পুরনো 'get_ff_edit_fields_kb' এর বদলে নতুনটি কল করুন
        await callback.message.edit_text(
            "কোন ধরণের তথ্য এডিট করতে চান?", 
            reply_markup=get_ff_edit_categories_kb(ff_id) # সঠিক নাম ✅
        )
    else:
        # যদি ইতিমধ্যে ক্যাটাগরিতে থাকে, তবে সেটি 'show_edit_categories' হ্যান্ডেল করবে
        # তাই এখানে অতিরিক্ত কিছু করার দরকার নেই, শুধু কলব্যাক পাস করুন।
        await show_edit_categories(callback)
        
    await callback.answer()

@router.callback_query(F.data.startswith("ff_field_"))
async def process_field_selection(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    
    # আইডি এবং ফিল্ডের নাম আলাদা করা
    ff_id = int(data_parts[-1])
    field_name = "_".join(data_parts[2:-1]) 
    
    async with async_session() as session:
        # ১. ডাটাবেজ থেকে মেম্বারের তথ্য নেওয়া
        m = await session.get(FieldForce, ff_id)
        if not m:
            return await callback.answer("❌ মেম্বার পাওয়া যায়নি।", show_alert=True)

        # ২. ডাইনামিকভাবে বর্তমান ভ্যালু সংগ্রহ করা ✅
        current_value = getattr(m, field_name)
        display_value = str(current_value) if current_value and str(current_value).lower() != 'nan' else "দেওয়া নেই"

        # ৩. ফিল্ডের নামকে সুন্দর বাংলায় রূপান্তর (ইউজার ফ্রেন্ডলি করার জন্য)
        # আপনি চাইলে এখানে একটি ডিকশনারি ব্যবহার করে আরও নিখুঁত নাম দিতে পারেন
        readable_name = field_name.replace('_', ' ').capitalize()

        # ৪. স্টেট আপডেট
        await state.update_data(edit_ff_id=ff_id, edit_field=field_name)
        
        # ৫. ইউজারকে বর্তমান তথ্যসহ মেসেজ দেওয়া
        text = (
            f"📝 **তথ্য আপডেট করুন**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📂 ফিল্ড: **{readable_name}**\n"
            f"📌 বর্তমান তথ্য: `{display_value}`\n\n"
            f"👉 নতুন তথ্যটি লিখে পাঠান (অথবা বাতিল করতে /start দিন):"
        )

        await callback.message.answer(text, parse_mode="Markdown")
        await state.set_state(FFStates.editing_value)
        await callback.answer()

# --- তথ্য আপডেট সেভ এবং সরাসরি প্রোফাইলে ফেরত যাওয়া ✅ ---
@router.message(FFStates.editing_value)
async def save_ff_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    edit_ff_id = data.get('edit_ff_id')
    edit_field = data.get('edit_field')

    async with async_session() as session:
        # ১. ডাটাবেজ থেকে মেম্বার লোড করা
        m = await session.get(FieldForce, edit_ff_id)
        if not m:
            await state.clear()
            return await message.answer("❌ মেম্বার পাওয়া যায়নি।")
        
        # ২. নতুন ডাটা সেট এবং সেভ করা
        new_value = message.text.strip()
        setattr(m, edit_field, new_value)
        await session.commit()
        
        # ডাটাবেজ থেকে লেটেস্ট তথ্য রিফ্রেশ করা
        await session.refresh(m)

        # ৩. প্রোফাইল টেক্সট এবং কিবোর্ড জেনারেট করা
        from app.Utils.helpers import get_field_force_full_profile_text
        from app.Views.keyboards.inline import get_ff_action_kb
        
        updated_details = get_field_force_full_profile_text(m)
        
        # ইউজার যদি সুপার এডমিন হয় তবে তাকে ডিলিট পারমিশনও দিব
        from config.settings import SUPER_ADMIN_ID
        is_admin = (int(message.from_user.id) == int(SUPER_ADMIN_ID))
        perms = ["edit_field_force"]
        if is_admin: perms.append("delete_field_force")
        
        kb = get_ff_action_kb(m.id, m.house_id, m.status, perms)

    # ৪. সাকসেস মেসেজ দেওয়া
    field_name = edit_field.replace('_', ' ').capitalize()
    await message.answer(f"✅ সফলভাবে **{field_name}** আপডেট করা হয়েছে।", parse_mode="Markdown")
    
    # ৫. স্টেট ক্লিয়ার করা
    await state.clear()

    # ৬. সরাসরি মেম্বারের আপডেট হওয়া প্রোফাইলটি পাঠানো ✅
    await message.answer(
        updated_details, 
        reply_markup=kb, 
        parse_mode="HTML"
    )

# ==========================================
# ৬. সার্চ লজিক
# ==========================================
@router.callback_query(F.data.startswith("ff_search_"))
async def start_ff_search(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    await state.update_data(search_house_id=house_id)
    await callback.message.answer("🔍 মেম্বারের নাম অথবা ডিএমএস কোড লিখে পাঠান:")
    await state.set_state(FFStates.searching)
    await callback.answer()

@router.message(FFStates.searching)
async def perform_ff_search(message: Message, state: FSMContext):
    query = message.text.strip()
    data = await state.get_data()
    house_id = data.get('search_house_id')

    async with async_session() as session:
        # নাম অথবা dms_code দিয়ে সার্চ
        res = await session.execute(
            select(FieldForce).where(
                FieldForce.house_id == house_id,
                or_(
                    FieldForce.name.icontains(query), 
                    FieldForce.dms_code.icontains(query) # এখানে dms_code সঠিক ছিল
                )
            )
        )
        results = res.scalars().all()
        
        if not results:
            return await message.answer("❌ কোনো মেম্বার পাওয়া যায়নি। পুনরায় চেষ্টা করুন বা /start দিন।")
        
        builder = InlineKeyboardBuilder()
        for r in results:
            # পরিবর্তন: r.code -> r.dms_code করা হয়েছে ✅ (এটিই ৩১৭ নম্বর লাইনের এরর ছিল)
            builder.button(text=f"👤 {r.name} ({r.dms_code})", callback_data=f"ff_view_{r.id}")
            
        builder.button(text="🔙 ব্যাকে যান", callback_data=f"ff_back_main_{house_id}")
        builder.adjust(1)
        
        await message.answer(f"🔍 সার্চ রেজাল্ট ({len(results)} জন):", reply_markup=builder.as_markup())
    await state.clear()

# ==========================================
# ৭. এক্সেল আপলোড ও ডিলিট
# ==========================================
@router.callback_query(F.data.startswith("ff_upload_"))
async def start_excel_upload(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[2])
    await state.update_data(upload_house_id=house_id)
    await callback.message.answer("📁 অনুগ্রহ করে ফিল্ড ফোর্স ডাটা সম্বলিত এক্সেল (.xlsx) ফাইলটি পাঠান।")
    await state.set_state(FFStates.waiting_for_excel)
    await callback.answer()

@router.message(FFStates.waiting_for_excel, F.document)
async def handle_excel_upload(message: Message, state: FSMContext):
    # ১. ফাইল ফরম্যাট চেক
    if not message.document.file_name.endswith('.xlsx'):
        return await message.answer("❌ ভুল ফাইল ফরম্যাট! শুধু .xlsx এক্সেল ফাইল গ্রহণ করা হয়।")
    
    # ২. স্টেট থেকে ডাটা নেওয়া
    data = await state.get_data()
    house_id = data.get('upload_house_id')
    
    if not house_id:
        return await message.answer("❌ সেশন এরর! অনুগ্রহ করে আবার হাউজ সিলেক্ট করে চেষ্টা করুন।")
    
    # --- হাউজের নাম খুঁজে বের করা ✅ ---
    async with async_session() as session:
        house = await session.get(House, house_id)
        h_name = house.name if house else "অজানা হাউজ"

    # ৩. ইনপুট ফাইল পাথ তৈরি এবং ডাউনলোড
    file_path = f"temp_ff_{message.from_user.id}.xlsx"
    wait_msg = await message.answer("⏳ ফাইলটি ডাউনলোড এবং প্রসেসিং শুরু হচ্ছে...")

    try:
        # টেলিগ্রাম থেকে ফাইল ডাউনলোড করা
        await message.bot.download(message.document, destination=file_path)

        # ৪. লাইভ আপডেট পাঠানোর ইন্টারনাল ফাংশন
        async def update_telegram_progress(text):
            try:
                # এখানেও হাউজের নাম ব্যবহার করা হয়েছে
                updated_text = f"{text}\n🏢 হাউজ: **{h_name}**"
                await wait_msg.edit_text(updated_text, parse_mode="Markdown")
            except:
                pass

        # ৫. এক্সেল প্রসেসিং সার্ভিস কল (প্রগ্রেস কলব্যাক সহ)
        count, err = await process_field_force_excel(
            file_path=file_path, 
            house_id=house_id, 
            progress_callback=update_telegram_progress
        )
        
        # ৬. রেজাল্ট হ্যান্ডেলিং
        if err:
            await wait_msg.edit_text(f"❌ **প্রসেসিং ব্যর্থ হয়েছে!**\n\nহাউজ: {h_name}\nএরর: `{err}`")
        else:
            await wait_msg.edit_text(
                f"✅ **আপলোড সম্পন্ন হয়েছে!**\n\n"
                f"📊 মোট রেকর্ড: `{bn_num(count)}` টি\n"
                f"🏢 হাউজ: **{h_name}**", # আইডি এর বদলে নাম ✅
                parse_mode="Markdown"
            )

            # ২. ৩ সেকেন্ড অপেক্ষা করা যাতে ইউজার সাকসেস মেসেজটি পড়ার সময় পায় ✅
            await asyncio.sleep(3)

            # ৩. ডাটাবেজ থেকে ওই হাউজের প্রথম পেজের মেম্বার লিস্ট নিয়ে আসা ✅
        async with async_session() as session:
            limit = 5 # প্রতি পেজে ৫ জন
            page = 1
            
            # টোটাল কাউন্ট এবং পেজ সংখ্যা বের করা
            total = await session.scalar(select(func.count(FieldForce.id)).where(FieldForce.house_id == house_id))
            total_pages = (total + limit - 1) // limit
            
            # মেম্বারদের ডাটা ফেচ করা
            res = await session.execute(
                select(FieldForce).where(FieldForce.house_id == house_id).limit(limit)
            )
            members = res.scalars().all()

            if members:
                # ৪. সাকসেস মেসেজটি এডিট করে মেম্বার লিস্টে রূপান্তর করা
                from app.Views.keyboards.inline import get_ff_pagination_kb
                kb = get_ff_pagination_kb(members, page, total_pages, house_id)
                
                await wait_msg.edit_text(
                    f"📋 **ফিল্ড ফোর্স মেম্বার তালিকা** (হাউজ: {h_name}):\n"
                    f"সদ্য আপলোড হওয়া ডাটাগুলো নিচে দেখুন।",
                    reply_markup=kb,
                    parse_mode="Markdown"
                )
            else:
                await wait_msg.answer("⚠️ ডাটা আপলোড হয়েছে কিন্তু লিস্ট লোড করা সম্ভব হয়নি।")


    except Exception as e:
        await wait_msg.edit_text(f"❌ **সিস্টেম এরর:** {str(e)}")

    finally:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        await state.clear()


# --- ডিলিট কনফার্মেশন ---
@router.callback_query(F.data.startswith("ff_del_conf_"), flags={"permission": "delete_field_force"})
async def confirm_delete(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[3])
    
    async with async_session() as session:
        # ১. ডাটাবেজ থেকে মেম্বারকে লোড করা যাতে নাম পাওয়া যায়
        m = await session.get(FieldForce, ff_id)
        if not m:
            return await callback.answer("❌ মেম্বার পাওয়া যায়নি।", show_alert=True)
        
        member_name = m.name

    # ২. বাটন তৈরি
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ হ্যাঁ, ডিলিট করুন", callback_data=f"ff_del_final_{ff_id}")
    builder.button(text="❌ না, বাতিল", callback_data=f"ff_view_{ff_id}")
    builder.adjust(2)

    # ৩. নামসহ মেসেজ তৈরি
    text = (
        f"⚠️ **সতর্কতা**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"আপনি কি নিশ্চিতভাবে মেম্বার **{member_name}**-কে ডাটাবেজ থেকে স্থায়ীভাবে মুছে ফেলতে চান?"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("ff_del_final_"))
async def final_delete(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        m = await session.get(FieldForce, ff_id)
        if m:
            name, house_id = m.name, m.house_id
            await session.delete(m)
            await session.commit()
            await callback.answer(f"🗑 {name} মুছে ফেলা হয়েছে।", show_alert=True)
            await render_ff_main(callback.message, house_id)
    await callback.answer()