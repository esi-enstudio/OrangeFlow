import os
import logging
import pandas as pd
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
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

# লগিং কনফিগারেশন (এই লাইনটি ইম্পোর্টগুলোর ঠিক নিচে বসান) ✅
logger = logging.getLogger(__name__)

router = Router()

class RetailerStates(StatesGroup):
    selected_house_id = State()
    waiting_for_excel = State()
    search_query = State()
    edit_field = State()
    edit_value = State()


# প্রতি পেজে কয়টি রিটেইলার দেখাবে
PAGE_LIMIT = 5

def get_retailer_full_profile_text(r: Retailer):
    """রিটেইলারের সকল ২০টি ফিল্ডের ডাটা HTML ফরম্যাটে সাজিয়ে দেওয়ার ফাংশন"""
    # ডাটাগুলো ক্লিন করা যাতে None থাকলে এরর না দেয়
    def clean(val):
        return str(val) if val else "N/A"
    
    return (
        f"🏪 **রিটেইলার বিস্তারিত প্রোফাইল**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 প্রাথমিক পরিচয়:</b>\n"
        f"🔹 নাম: {r.name}\n"
        f"🔹 কোড: `{r.retailer_code}`\n"
        f"🔹 টাইপ: {r.type or 'N/A'}\n"
        f"🔹 সচল (Enabled): {r.enabled or 'N/A'}\n\n"
        
        f"<b>📞 যোগাযোগ ও মোবাইল:</b>\n"
        f"🔹 ফোন নং: {r.contact_no or 'N/A'}\n"
        f"🔹 iTop No: {r.itop_number or 'N/A'}\n"
        f"🔹 iTop SR No: {r.itop_sr_number or 'N/A'}\n"
        f"🔹 Tran Mobile: {r.tran_mobile_no or 'N/A'}\n\n"
        
        f"<b>📍 ঠিকানা ও লোকেশন:</b>\n"
        f"🔹 জেলা: {r.district or 'N/A'}\n"
        f"🔹 থানা: {r.thana or 'N/A'}\n"
        f"🔹 রুট: {r.route or 'N/A'}\n"
        f"🔹 ঠিকানা: {r.address or 'N/A'}\n\n"
        
        f"<b>👤 মালিক ও ব্যক্তিগত তথ্য:</b>\n"
        f"🔹 মালিকের নাম: {r.owner_name or 'N/A'}\n"
        f"🔹 NID: {r.nid or 'N/A'}\n"
        f"🔹 জন্মতারিখ: {r.dob or 'N/A'}\n\n"
        
        f"<b>💼 বিজনেজ ডিটেইলস:</b>\n"
        f"🔹 ক্যাটাগরি: {r.category or 'N/A'}\n"
        f"🔹 সার্ভিস পয়েন্ট: {r.service_point or 'N/A'}\n"
        f"🔹 সিম সেলার: {r.sim_seller or 'N/A'}\n\n"
        
        f"<b>👷‍♂️ বিপি (BP) কানেকশন:</b>\n"
        f"🔹 BP কোড: {r.bp_code or 'N/A'}\n"
        f"🔹 BP নম্বর: {r.bp_number or 'N/A'}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


# --- ১. প্রবেশ পথ (হাউজ চেক) ---
@router.message(F.text == "🏪 রিটেইলারস", flags={"permission": "manage_retailer"})
async def retailer_main(message: Message, state: FSMContext, permissions: list):
    await state.clear()
    async with async_session() as session:
        # ইউজারের হাউজগুলো লোড করা
        res = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == message.from_user.id)
        )
        user = res.scalar_one_or_none()
        
        # ১. সুপার এডমিন চেক ✅
        if int(message.from_user.id) == int(SUPER_ADMIN_ID):
            # সুপার এডমিন যদি কোনো হাউজের সাথে সরাসরি যুক্ত নাও থাকে, সে সব হাউজ দেখতে পারবে
            h_res = await session.execute(select(House))
            all_houses = h_res.scalars().all()
            
            if not all_houses:
                return await message.answer("❌ সিস্টেমে কোনো হাউজ তৈরি করা নেই।")
            
            builder = InlineKeyboardBuilder()
            for h in all_houses:
                builder.button(text=f"🏢 {h.name}", callback_data=f"ret_hsel_{h.id}")
            builder.adjust(1)
            return await message.answer("সুপার এডমিন প্যানেল: হাউজ নির্বাচন করুন", reply_markup=builder.as_markup())
        
        if not user or not user.houses:
            return await message.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।")

        # যদি ১টি হাউজ থাকে
        if len(user.houses) == 1:
            house = user.houses[0]
            await state.update_data(selected_house_id=house.id)
            return await show_house_retailer_menu(message, house.id, house.name, permissions)

        # যদি একাধিক হাউজ থাকে
        builder = InlineKeyboardBuilder()
        for h in user.houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"ret_hsel_{h.id}")
        builder.adjust(1)
        await message.answer("আপনার একাধিক হাউজ রয়েছে। কোন হাউজের রিটেইলার ম্যানেজ করতে চান?", reply_markup=builder.as_markup())

# হাউজ সিলেক্ট করার পর মেনু দেখানোর কলব্যাক
@router.callback_query(F.data.startswith("ret_hsel_"))
async def handle_retailer_house_selection(callback: CallbackQuery, state: FSMContext, permissions: list):
    house_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house: return await callback.answer("হাউজ পাওয়া যায়নি")
        
        await state.update_data(selected_house_id=house.id)
        await callback.message.delete()
        # এখানে state পাস করা হয়েছে
        await show_house_retailer_menu(callback.message, house.id, house.name, permissions)

# কমন ফাংশন: নির্দিষ্ট হাউজের রিটেইলার মেনু দেখানো
async def show_house_retailer_menu(message: Message, house_id: int, house_name: str, permissions: list):
    async with async_session() as session:
        count = await session.scalar(select(func.count(Retailer.id)).where(Retailer.house_id == house_id))

    builder = InlineKeyboardBuilder()
    if count > 0 and "view_retailer" in permissions:
        builder.button(text="📋 লিস্ট দেখুন", callback_data="ret_list_0")
        builder.button(text="🔍 সার্চ করুন", callback_data="ret_search_start")
    
    if "upload_retailer_excel" in permissions:
        builder.button(text="📤 এক্সել আপলোড", callback_data="ret_upload_start")
        builder.button(text="📥 স্যাম্পল ডাউনলোড", callback_data="ret_sample_dl")
        
    builder.adjust(2)
    text = f"🏪 **রিটেইলার ম্যানেজমেন্ট**\n🏢 হাউজ: **{house_name}**"
    text += f"\n\n📊 এই হাউজে মোট `{count}` জন রিটেইলার আছে।" if count > 0 else "\n\n⚠️ কোনো রিটেইলার নেই। ফাইল আপলোড করুন।"
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ৪. স্যাম্পল ফাইল ডাউনলোড লজিক ✅ ---
@router.callback_query(F.data == "ret_sample_dl", flags={"permission": "upload_retailer_excel"})
async def download_retailer_sample(callback: CallbackQuery):
    file_name = "Retailer_List_Template.xlsx"
    
    # ডিএমএস এর এক্সেল হেডার অনুযায়ী কলাম লিস্ট
    columns = [
        'CLUSTERNAME', 'REGION', 'DISTRIBUTOR_CODE', 'RETAILER_CODE', 'RETAILER_NAME', 
        'RETAILER_TYPE', 'ENABLED', 'SIM_SELLER', 'TRANMOBILENO', 'I_TOP_UP_SR_NUMBER', 
        'I_TOP_UP_NUMBER', 'SERVICE_POINT', 'CATEGORY', 'OWNER_NAME', 'CONTACT_NO', 
        'DISTRICT', 'THANA', 'ADDRESS', 'NID', 'BP_CODE', 'BP_NUMBER', 'DOB', 'ROUTE'
    ]
    
    try:
        # একটি খালি এক্সেল ফাইল তৈরি করা
        df = pd.DataFrame(columns=columns)
        df.to_excel(file_name, index=False)
        
        # টেলিগ্রামে ফাইলটি পাঠানো
        sample_file = FSInputFile(file_name)
        await callback.message.answer_document(
            sample_file, 
            caption="📥 **রিটেইলার লিস্ট টেমপ্লেট**\n\nএই ফাইলটি পূরণ করে বটে আপলোড করুন। নিশ্চিত করুন যে 'RETAILER_CODE' কলামটি সঠিক আছে।"
        )
        
        # পাঠানোর পর পিসি থেকে ফাইলটি ডিলিট করে দেওয়া
        if os.path.exists(file_name):
            os.remove(file_name)
            
        await callback.answer("ফাইল পাঠানো হয়েছে")
    except Exception as e:
        logger.error(f"Error generating sample file: {e}")
        await callback.answer("❌ ফাইল তৈরিতে সমস্যা হয়েছে", show_alert=True)


# --- ২. এক্সেল ফাইল রিসিভ এবং প্রসেস ✅ ---
@router.callback_query(F.data == "ret_upload_start", flags={"permission": "upload_retailer_excel"})
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 ডিএমএস থেকে ডাউনলোড করা **Retailer List** এক্সেল ফাইলটি পাঠান।")
    await state.set_state(RetailerStates.waiting_for_excel)
    await callback.answer()

@router.message(RetailerStates.waiting_for_excel, F.document)
async def handle_retailer_file(message: Message, state: FSMContext):
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    
    if not house_id:
        return await message.answer("❌ সেশন আউট! দয়া করে আবার /start থেকে রিটেইলার মেনুতে ঢুকুন।")
    
    wait_msg = await message.answer("⏳ ফাইল প্রসেস হচ্ছে, দয়া করে অপেক্ষা করুন...")

    # ফাইল ডাউনলোড
    file_path = f"temp_ret_{message.from_user.id}.xlsx"
    await message.bot.download(message.document, destination=file_path)
    
    # ডাটাবেজ আপডেট (হাউজ আইডি সহ)
    count, err = await process_retailer_excel(file_path, house_id)
    
    if os.path.exists(file_path): os.remove(file_path)
    
    if err:
        await wait_msg.edit_text(f"❌ এরর: {err}")
    else:
        await wait_msg.edit_text(f"✅ সফল! এই হাউজের জন্য মোট {bn_num(count)}টি রিটেইলার আপডেট করা হয়েছে।")
    
    await state.set_state(None) # শুধুমাত্র ফাইল স্টেট ক্লিয়ার করবে, হাউজ আইডি নয়


# --- ২. রিটেইলার লিস্ট (স্মার্ট পেজিনেশন) ---
@router.callback_query(F.data.startswith("ret_list_"), flags={"permission": "view_retailer"})
async def list_retailers(callback: CallbackQuery, state: FSMContext, permissions: list):
    offset = int(callback.data.split("_")[2])
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    
    if not house_id:
        return await callback.message.answer("❌ হাউজ সিলেক্ট করা নেই। দয়া করে মেইন মেনু থেকে আবার ঢুকুন।")

    house_id = data.get('selected_house_id')

    async with async_session() as session:
        # শুধুমাত্র নির্দিষ্ট হাউজের কাউন্ট এবং ডাটা ✅
        total_count = await session.scalar(select(func.count(Retailer.id)).where(Retailer.house_id == house_id))
        
        res = await session.execute(
            select(Retailer).where(Retailer.house_id == house_id).order_by(Retailer.name).limit(PAGE_LIMIT).offset(offset)
        )

        retailers = res.scalars().all()

        builder = InlineKeyboardBuilder()
        for r in retailers:
            builder.button(text=f"🏪 {r.name} ({r.retailer_code})", callback_data=f"ret_view_{r.id}")
        builder.adjust(1)

        # পেজিনেশন লজিক: যদি ৫ জনের বেশি থাকে তবেই বাটন দেখাবে ✅
        nav_btns = []
        if offset > 0:
            nav_btns.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"ret_list_{offset - PAGE_LIMIT}"))
        if offset + PAGE_LIMIT < total_count:
            nav_btns.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"ret_list_{offset + PAGE_LIMIT}"))
        
        if nav_btns:
            builder.row(*nav_btns)
        
        builder.row(InlineKeyboardButton(text="🔙 মেইন মেনু", callback_data="ret_back_main"))
        
        await callback.message.edit_text(f"📋 **রিটেইলার তালিকা** (মোট: {total_count} জন):", reply_markup=builder.as_markup())

# --- ৩. রিটেইলার বিস্তারিত তথ্য (সকল ২০টি কলাম) ---
@router.callback_query(F.data.startswith("ret_view_"), flags={"permission": "view_retailer"})
async def view_retailer_details(callback: CallbackQuery, permissions: list):
    ret_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        r = await session.get(Retailer, ret_id)
        if not r: return await callback.answer("রিটেইলার পাওয়া যায়নি।")

        # হেল্পার ফাংশন থেকে টেক্সট জেনারেট করা ✅
        text = get_retailer_full_profile_text(r)
        
        builder = InlineKeyboardBuilder()
        if "edit_retailer" in permissions:
            builder.button(text="✏️ তথ্য এডিট", callback_data=f"ret_edit_menu_{r.id}")
        if "delete_retailer" in permissions:
            builder.button(text="🗑 ডিলিট করুন", callback_data=f"ret_conf_del_{r.id}")
        
        builder.button(text="🔙 লিস্টে ফিরুন", callback_data="ret_list_0")
        builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# --- ৪. এডিট লজিক (সকল কলাম ডাইনামিক) ---
@router.callback_query(F.data.startswith("ret_edit_menu_"), flags={"permission": "edit_retailer"})
async def show_retailer_edit_fields(callback: CallbackQuery):
    ret_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()
    
    # সকল ফিল্ডের তালিকা (ডাটাবেজ কলাম অনুযায়ী)
    fields = [
        ("নাম", "name"), ("কোড", "code"), ("টাইপ", "type"), ("সচল", "enabled"),
        ("সিম সেলার", "sim_seller"), ("ফোন নং", "contact_no"), ("iTop No", "itop_number"),
        ("SR নং", "itop_sr_number"), ("Tran Mobile", "tran_mobile_no"), ("জেলা", "district"),
        ("থানা", "thana"), ("রুট", "route"), ("ঠিকানা", "address"), ("মালিক", "owner_name"),
        ("NID", "nid"), ("DOB", "dob"), ("ক্যাটাগরি", "category"), ("সার্ভিস পয়েন্ট", "service_point"),
        ("BP কোড", "bp_code"), ("BP নম্বর", "bp_number")
    ]

    for label, field in fields:
        # এখানে বিভাজক হিসেবে ':' ব্যবহার করছি যাতে আন্ডারস্কোর নিয়ে সমস্যা না হয় ✅
        builder.button(text=f"📝 {label}", callback_data=f"retedit:{field}:{ret_id}")
    
    builder.button(text="🔙 ফিরে যান", callback_data=f"ret_view_{ret_id}")
    builder.adjust(2)
    await callback.message.edit_text("কোন তথ্যটি পরিবর্তন করতে চান?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("retedit:"), flags={"permission": "edit_retailer"})
async def start_retailer_edit_input(callback: CallbackQuery, state: FSMContext):
    # কোলন (:) দিয়ে ডাটা আলাদা করা হচ্ছে যা অনেক বেশি নিরাপদ ✅
    parts = callback.data.split(":")
    field = parts[1]
    ret_id = int(parts[2])
    
    async with async_session() as session:
        # ১. ডাটাবেজ থেকে রিটেইলারের বর্তমান তথ্য নেওয়া
        r = await session.get(Retailer, ret_id)
        
        if not r:
            return await callback.answer("❌ রিটেইলার পাওয়া যায়নি।", show_alert=True)

        # ২. ডাইনামিকভাবে ওই নির্দিষ্ট ফিল্ডের বর্তমান ভ্যালু বের করা
        current_val = getattr(r, field)
        
        # যদি ভ্যালু খালি থাকে তবে 'দেওয়া নেই' দেখাবে
        if current_val is None or str(current_val).strip() == "":
            current_val = "_(বর্তমানে খালি আছে)_"
        else:
            current_val = f"`{current_val}`"

        # ৩. ফিল্ডের নাম সুন্দর করে সাজানো (উদা: itop_number -> ITOP NUMBER)
        display_field = field.replace("_", " ").upper()

        # ৪. স্টেট আপডেট করা
        await state.update_data(edit_ret_id=ret_id, edit_field=field)
        
        # ৫. ইউজারকে মেসেজ পাঠানো
        text = (
            f"📝 **{display_field} পরিবর্তন**\n\n"
            f"🕒 বর্তমান তথ্য: {current_val}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 রিটেইলারের নতুন **{display_field}** লিখে পাঠান:"
        )
        
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
        await state.set_state(RetailerStates.edit_value)


@router.message(RetailerStates.edit_value)
async def save_retailer_edit(message: Message, state: FSMContext, permissions: list):
    data = await state.get_data()
    ret_id = data.get('edit_ret_id')
    field_name = data.get('edit_field')
    new_val = message.text.strip()

    async with async_session() as session:
        # ১. ডাটাবেজ থেকে রিটেইলার খুঁজে বের করা
        r = await session.get(Retailer, ret_id)

        if not r:
            await state.set_state(None) # এটি করলে ইনপুট নেওয়ার প্রসেস বন্ধ হবে কিন্তু 'selected_house_id' মেমোরিতে থেকে যাবে।

            return await message.answer("❌ রিটেইলার পাওয়া যায়নি।")
        
        # ২. ডাইনামিক আপডেট
        old_val = getattr(r, field_name)
        setattr(r, field_name, new_val)
        await session.commit()

        # ৩. সাকসেস মেসেজ পাঠানো
        await message.answer(f"✅ সফলভাবে **{field_name.replace('_', ' ').upper()}** আপডেট করা হয়েছে।\n`{old_val}` ➡️ `{new_val}`", parse_mode="HTML")

        # আপডেট হওয়া সকল তথ্য পুনরায় দেখানো ✅
        text = get_retailer_full_profile_text(r)

        builder = InlineKeyboardBuilder()
        if "edit_retailer" in permissions:
            builder.button(text="✏️ আরও এডিট করুন", callback_data=f"ret_edit_menu_{r.id}")
        
        builder.button(text="📋 লিস্টে ফিরুন", callback_data="ret_list_0")
        builder.button(text="🔙 মেইন মেনু", callback_data="ret_back_main")
        builder.adjust(2)

        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    # কাজ শেষ, স্টেট ক্লিয়ার
    await state.clear()

# --- ৫. ডিলিট লজিক (কনফার্মেশন সহ) ✅ ---
@router.callback_query(F.data.startswith("ret_conf_del_"), flags={"permission": "delete_retailer"})
async def confirm_retailer_delete(callback: CallbackQuery):
    ret_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ হ্যাঁ, ডিলিট করুন", callback_data=f"ret_final_del_{ret_id}")
    builder.button(text="❌ না, বাতিল", callback_data=f"ret_view_{ret_id}")
    builder.adjust(2)
    await callback.message.edit_text("⚠️ **সতর্কবার্তা!**\nআপনি কি নিশ্চিতভাবে এই রিটেইলারকে মুছে ফেলতে চান? এটি আর ফিরিয়ে আনা যাবে না।", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("ret_final_del_"), flags={"permission": "delete_retailer"})
async def final_retailer_delete(callback: CallbackQuery, permissions: list):
    """চূড়ান্তভাবে ডিলিট করার পর মেসেজ রিফ্রেশ করবে"""
    ret_id = int(callback.data.split("_")[3])

    async with async_session() as session:
        # ১. ডাটাবেজ থেকে রিটেইলারটি খুঁজে বের করা
        r = await session.get(Retailer, ret_id)

        if r:
            name = r.name
            # ২. ডিলিট করা
            await session.delete(r)
            await session.commit()
            # ৩. স্ক্রিনের উপরে ছোট সাকসেস এলার্ট দেখানো
            await callback.answer(f"🗑 {name} স্থায়ীভাবে মুছে ফেলা হয়েছে।", show_alert=True)
        else:
            await callback.answer("❌ রিটেইলারটি ইতিমধ্যে মুছে ফেলা হয়েছে বা পাওয়া যায়নি।")

    
    # ৪. অত্যন্ত গুরুত্বপূর্ণ: সতর্কবার্তার মেসেজটি এডিট করে আবার লিস্টে পাঠিয়ে দেওয়া ✅
    # এতে করে সতর্কবার্তার লেখা এবং ডিলিট বাটনগুলো গায়েব হয়ে যাবে এবং ফ্রেশ লিস্ট চলে আসবে।
    try:
        await list_retailers(callback, permissions)
    except Exception as e:
        # যদি কোনো কারণে লিস্ট রিফ্রেশ না হয়, তবে মেইন মেনুতে পাঠিয়ে দিবে
        logger.error(f"Error refreshing list after delete: {e}")
        await callback.message.delete() # সতর্কবার্তাটি ডিলিট করে দিবে
        await retailer_main(callback.message, permissions)

# --- ১. সার্চ শুরু করার ট্রিগার (বাটন ক্লিক) ---
@router.callback_query(F.data == "ret_search_start", flags={"permission": "view_retailer"})
async def search_start(callback: CallbackQuery, state: FSMContext):
    await state.clear() # আগের সব স্টেট ক্লিয়ার করবে
    
    # ইনলাইন বাটন দিয়ে বাতিলের সুযোগ রাখা
    cancel_kb = InlineKeyboardBuilder().button(text="❌ বাতিল করুন", callback_data="ret_list_0").as_markup()
    
    await callback.message.answer(
        "🔍 **রিটেইলার সার্চ**\n\nরিটেইলারের **নাম** অথবা **কোড (R-Code)** লিখে পাঠান:",
        reply_markup=cancel_kb
    )
    
    # ইউজারকে সার্চ কুয়েরি স্টেটে নিয়ে যাওয়া
    await state.set_state(RetailerStates.search_query)
    await callback.answer()

# --- ২. সার্চ রেজাল্ট প্রসেসিং (ইউজার টেক্সট পাঠানোর পর) ---
@router.message(RetailerStates.search_query)
async def process_search(message: Message, state: FSMContext, permissions: list):
    query_text = message.text.strip()
    
    # স্টেট থেকে সিলেক্ট করা হাউজ আইডি নেওয়া
    data = await state.get_data()
    house_id = data.get('selected_house_id')
    
    if not house_id:
        return await message.answer("❌ সেশন টাইমআউট! দয়া করে আবার রিটেইলার মেনুতে ঢুকুন।")

    if len(query_text) < 2:
        return await message.answer("⚠️ অন্তত ২ অক্ষরের নাম বা কোড লিখুন।")

    async with async_session() as session:
        # SQL LIKE অপারেটর ব্যবহার করে নাম বা কোডে খোঁজা (হাউজ ফিল্টারসহ)
        search_pattern = f"%{query_text}%"
        res = await session.execute(
            select(Retailer).where(
                Retailer.house_id == house_id, # শুধুমাত্র সিলেক্ট করা হাউজের ডাটা ✅
                or_(
                    Retailer.name.ilike(search_pattern), 
                    Retailer.retailer_code.ilike(search_pattern)
                )
            ).limit(10)
        )
        retailers = res.scalars().all()
        
        if not retailers:
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 আবার চেষ্টা করুন", callback_data="ret_search_start")
            builder.button(text="🔙 ব্যাকে যান", callback_data="ret_list_0")
            return await message.answer(
                f"❌ '{query_text}' নামে কোনো রিটেইলার পাওয়া যায়নি।", 
                reply_markup=builder.adjust(1).as_markup()
            )

        # রেজাল্ট লিস্ট তৈরি
        builder = InlineKeyboardBuilder()
        for r in retailers:
            # বাটন টেক্সটে রিটেইলার কোড দেখানো হচ্ছে
            builder.button(text=f"🏪 {r.name} ({r.retailer_code})", callback_data=f"ret_view_{r.id}")
        
        builder.button(text="🔍 নতুন সার্চ", callback_data="ret_search_start")
        builder.button(text="🔙 ব্যাকে যান", callback_data="ret_list_0")
        builder.adjust(1)

        await message.answer(
            f"✅ <b>সার্চ রেজাল্ট:</b> ({len(retailers)} জন পাওয়া গেছে)\nনিচের বাটনে ক্লিক করে বিস্তারিত দেখুন:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    # হাউজ আইডি মেমোরিতে রেখে শুধু ইনপুট স্টেট ক্লিয়ার করা ✅
    await state.set_state(None)


# ব্যাক টু রিটেইলার মেইন
@router.callback_query(F.data == "ret_back_main")
async def back_to_retailer_main(callback: CallbackQuery, state: FSMContext, permissions: list):
    await callback.message.delete()
    # এখানে state পাস করা হয়েছে যাতে ক্রাশ না করে
    await retailer_main(callback.message, state, permissions)