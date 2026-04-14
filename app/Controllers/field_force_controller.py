import os
import logging

from aiogram import Router, F, types
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

async def handle_ff_house_logic(message, state, user_tg_id, is_callback=False):
    async with async_session() as session:
        res = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
        )
        user = res.scalar_one_or_none()
        
        if not user or not user.houses:
            msg_text = "❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।"
            return await message.edit_text(msg_text) if is_callback else await message.answer(msg_text)

        if len(user.houses) == 1:
            await render_ff_main(message, user.houses[0].id, is_callback)
        else:
            kb = get_field_force_house_selection_kb(user.houses)
            if is_callback: await message.edit_text("🏢 **হাউজ নির্বাচন করুন:**", reply_markup=kb)
            else: await message.answer("🏢 **হাউজ নির্বাচন করুন:**", reply_markup=kb)


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
        
        # ২. ইউজারের পারমিশন চেক (মিডলওয়্যার থেকে যা পাওয়া যাবে)
        # ধরা যাক আপনার রোলে 'view_all_field_force' নামে একটি পারমিশন আছে
        
        # ৩. এই ইউজারের সাথে কোন প্রোফাইল লিঙ্ক করা আছে কি না দেখা
        ff_res = await session.execute(
            select(FieldForce.id).where(FieldForce.user_id == (
                select(User.id).where(User.telegram_id == user_tg_id).scalar_subquery()
            ))
        )
        personal_ff_id = ff_res.scalar_one_or_none()
        
        house = await session.get(House, house_id)
        total_count = await session.scalar(
            select(func.count(FieldForce.id)).where(FieldForce.house_id == house_id)
        )

        text = (
            f"🏪 **ফিল্ড ফোর্স ম্যানেজমেন্ট**\n"
            f"🏢 হাউজ: **{house.name}**\n\n"
            f"📊 মোট মেম্বার: **{bn_num(total_count)}** জন"
        )
        
        # ৪. এডমিন ভিউ বনাম পার্সোনাল ভিউ সিদ্ধান্ত
        # যদি সুপার এডমিন হয় অথবা যার কাছে 'manage_field_force' পারমিশন আছে
        is_admin_view = is_super_admin # প্রয়োজনে এখানে পারমিশন চেক যোগ করবেন
        
        kb = get_field_force_main_kb(
            house_id, total_count, [], 
            is_admin=is_admin_view, 
            personal_ff_id=personal_ff_id
        )
        
        if is_callback: await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else: await message.answer(text, reply_markup=kb, parse_mode="Markdown")


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
        from app.Views.keyboards.inline import get_ff_action_kb
        
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
@router.callback_query(F.data.startswith("ff_edit_"), flags={"permission": "edit_field_force"})
async def show_edit_categories(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    # সব সময় শেষের এলিমেন্টটি আইডি হিসেবে নিবে (নিরাপদ পদ্ধতি)
    ff_id = int(data_parts[-1]) 

    if "cat_" in callback.data:
        # এটি ক্যাটাগরি সিলেকশন (Format: ff_edit_cat_cat_name_ID)
        # এখানে ৩ নম্বর এবং ৪ নম্বর পার্ট মিলে ক্যাটাগরি নাম তৈরি হবে
        category = f"{data_parts[2]}_{data_parts[3]}" # যেমন: cat_basic
        await callback.message.edit_text(
            "কোন ফিল্ডটি আপডেট করতে চান?", 
            reply_markup=get_ff_fields_by_category_kb(category, ff_id)
        )
    else:
        # এটি প্রাথমিক এডিট বাটন ক্লিক (Format: ff_edit_ID)
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
    # শেষ অংশ আইডি এবং মাঝের অংশগুলো ফিল্ডের নাম
    ff_id = int(data_parts[-1])
    field = "_".join(data_parts[2:-1]) # যেমন: phone_number
    
    await state.update_data(edit_ff_id=ff_id, edit_field=field)
    
    # সুন্দর নাম দেখানোর জন্য
    display_name = field.replace('_', ' ').capitalize()
    await callback.message.answer(f"মেম্বারের নতুন **{display_name}** লিখে পাঠান:")
    await state.set_state(FFStates.editing_value)
    await callback.answer()

# --- ডাইনামিক ফিল্ড সেভ (অপরিবর্তিত কিন্তু শক্তিশালী) ---
@router.message(FFStates.editing_value)
async def save_ff_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        m = await session.get(FieldForce, data['edit_ff_id'])
        
        # ডাইনামিকভাবে ফিল্ড আপডেট
        new_val = message.text.strip()
        setattr(m, data['edit_field'], new_val)
        await session.commit()
        
        logger.info(f"✅ Field {data['edit_field']} updated for FF ID {m.id} by {message.from_user.id}")
        house_id = m.house_id
        ff_id = m.id
    
    await state.clear()
    await message.answer(f"✅ সফলভাবে **{data['edit_field'].replace('_', ' ')}** আপডেট হয়েছে।")
    
    # অটোমেটিক পুনরায় প্রোফাইল ভিউতে নিয়ে যাবে
    # প্রোফাইল দেখানোর জন্য একটি ডামি কলব্যাক অবজেক্ট তৈরি করা যায় অথবা সরাসরি মেথড কল
    await render_ff_main(message, house_id)

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

    except Exception as e:
        await wait_msg.edit_text(f"❌ **সিস্টেম এরর:** {str(e)}")

    finally:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        await state.clear()


@router.callback_query(F.data.startswith("ff_del_conf_"), flags={"permission": "delete_field_force"})
async def confirm_delete(callback: CallbackQuery):
    ff_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ নিশ্চিত ডিলিট", callback_data=f"ff_del_final_{ff_id}")
    builder.button(text="❌ বাতিল", callback_data=f"ff_view_{ff_id}")
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে এই মেম্বারকে ডাটাবেজ থেকে মুছে ফেলতে চান?", reply_markup=builder.as_markup())

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