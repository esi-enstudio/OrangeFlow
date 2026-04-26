import os
import unicodedata
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.Models.bts import BTS
from app.Models.user import User
from app.Models.house import House
from app.Services.db_service import async_session
from app.Services.Automation.bts_excel import process_bts_excel, generate_bts_sample
from app.Views.keyboards.inline import get_bts_pagination_kb, get_bts_search_results_kb
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

class BTSStates(StatesGroup):
    selected_house_id = State()
    waiting_for_excel = State()
    search_query = State()
    edit_value = State()

PAGE_LIMIT = 5

# ==========================================
# ১. প্রোফাইল টেক্সট হেল্পার (Grouped HTML)
# ==========================================
def get_bts_full_profile_text(b: BTS):
    """বিটিএস-এর সকল ২৭টি কলামের ডাটা HTML ফরম্যাটে সাজিয়ে দেওয়ার ফাংশন"""
    def clean(val): 
        return str(val) if val and str(val).lower() != 'nan' else "N/A"
    
    return (
        f"📡 <b>বিটিএস বিস্তারিত প্রোফাইল</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 পরিচয় (Identification):</b>\n"
        f"🔹 Site ID: <code>{b.site_id}</code>\n"
        f"🔹 BTS Code: <code>{b.bts_code}</code>\n"
        f"🔹 Site Type: {clean(b.site_type)}\n"
        f"🔹 Priority: {clean(b.priority)}\n"
        f"🔹 Distributor Code: {clean(b.distributor_code)}\n\n"

        f"<b>📍 অবস্থান - ইংরেজি (Geography EN):</b>\n"
        f"🔹 Thana: {clean(b.thana)}\n"
        f"🔹 District: {clean(b.district)}\n"
        f"🔹 Division: {clean(b.division)}\n"
        f"🔹 Cluster: {clean(b.cluster)}\n"
        f"🔹 Region: {clean(b.region)}\n\n"

        f"<b>📍 অবস্থান - বাংলা (Geography BN):</b>\n"
        f"🔹 থানা: {clean(b.thana_bn)}\n"
        f"🔹 জেলা: {clean(b.district_bn)}\n"
        f"🔹 বিভাগ: {clean(b.division_bn)}\n"
        f"🔹 ক্লাস্টার: {clean(b.cluster_bn)}\n"
        f"🔹 রিজিয়ন: {clean(b.region_bn)}\n\n"

        f"<b>🌐 নেটওয়ার্ক ও ঠিকানা (Technical & Address):</b>\n"
        f"🔹 Mode: {clean(b.network_mode)}\n"
        f"🔹 Urban/Rural: {clean(b.urban_rural)}\n"
        f"🔹 Archetype: {clean(b.archetype)}\n"
        f"🔹 Market: {clean(b.market)}\n"
        f"🔹 Short Address: {clean(b.short_address)}\n"
        f"🔹 Address EN: {clean(b.address)}\n"
        f"🔹 ঠিকানা (বাংলা): {clean(b.address_bn)}\n"
        f"🔹 Longitude: {clean(b.longitude)}\n"
        f"🔹 Latitude: {clean(b.latitude)}\n\n"

        f"<b>📅 এয়ার ডেট (On-Air Timeline):</b>\n"
        f"🔹 2G On-Air: {clean(b.onair_date_2g)}\n"
        f"🔹 3G On-Air: {clean(b.onair_date_3g)}\n"
        f"🔹 4G On-Air: {clean(b.onair_date_4g)}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ==========================================
# ২. এন্ট্রি এবং হাউজ সিলেকশন
# ==========================================
@router.message(F.text == "📡 বিটিএস লিস্ট", flags={"permission": "view_bts"})
async def bts_main_entry(message: Message, state: FSMContext, permissions: list):
    await state.clear()
    user_id = message.from_user.id
    
    async with async_session() as session:
        # সুপার এডমিন চেক
        if int(user_id) == int(SUPER_ADMIN_ID):
            houses = (await session.execute(select(House))).scalars().all()
        else:
            user = (await session.execute(select(User).options(selectinload(User.houses)).where(User.telegram_id == user_id))).scalar_one_or_none()
            houses = user.houses if user else []

        if not houses: return await message.answer("❌ কোনো হাউজ যুক্ত নেই।")
        
        if len(houses) == 1:
            return await render_bts_dashboard(message, houses[0].id, permissions)

        builder = InlineKeyboardBuilder()
        for h in houses: builder.button(text=f"🏢 {h.name}", callback_data=f"bts_hsel_{h.id}")
        await message.answer("📡 **বিটিএস ম্যানেজমেন্ট**\nহাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())

@router.callback_query(F.data.startswith("bts_hsel_"))
async def handle_bts_house_select(callback: CallbackQuery, state: FSMContext, permissions: list):
    house_id = int(callback.data.split("_")[2])
    await state.update_data(selected_house_id=house_id)
    await callback.message.delete()
    await render_bts_dashboard(callback.message, house_id, permissions)

async def render_bts_dashboard(message: Message, house_id: int, permissions: list):
    async with async_session() as session:
        house = await session.get(House, house_id)
        count = await session.scalar(select(func.count(BTS.id)).where(BTS.house_id == house_id))

    builder = InlineKeyboardBuilder()
    if count > 0:
        builder.button(text="📋 লিস্ট দেখুন", callback_data=f"bts_list_{house_id}_0")
        builder.button(text="🔍 সার্চ করুন", callback_data=f"bts_search_start")
    if "create_bts" in permissions:
        builder.button(text="📤 এক্সেল আপলোড", callback_data="bts_upload_start")
    builder.button(text="📥 স্যাম্পল ডাউনলোড", callback_data="bts_sample_dl")
    builder.button(text="🔄 হাউজ পরিবর্তন", callback_data="bts_change_house")
    
    text = f"📡 <b>বিটিএস ম্যানেজমেন্ট</b>\n🏢 হাউজ: <b>{house.name}</b>\n📊 মোট বিটিএস: <code>{bn_num(count)}</code> টি"
    await message.answer(text, reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")

# ==========================================
# ৩. লিস্ট এবং পেজিনেশন (পাশাপাশি বাটন)
# ==========================================
# ১. থানা সিলেকশন মেনু
@router.callback_query(F.data.startswith("bts_list_"))
async def list_thana_selection(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        # ওই হাউজের সব ইউনিক থানার নাম (বাংলায়) সংগ্রহ ✅
        res = await session.execute(
            select(BTS.thana_bn).where(BTS.house_id == house_id).distinct().order_by(BTS.thana_bn)
        )
        thanas = res.scalars().all()

        if not thanas:
            return await callback.answer("⚠️ কোনো ডাটা পাওয়া যায়নি।", show_alert=True)

        builder = InlineKeyboardBuilder()
        for thana in thanas:
            t_name = thana if thana else "অজানা থানা"
            # কলব্যাক ফরম্যাট: btsthana_{house_id}_{thana_name}
            builder.button(text=f"📍 {t_name}", callback_data=f"btsthana:{house_id}:{t_name}")
        
        builder.adjust(2)
        builder.row(InlineKeyboardButton(text="🔙 ব্যাকে যান", callback_data=f"bts_hsel_{house_id}"))

        await callback.message.edit_text(
            "🏘 <b>থানা নির্বাচন করুন:</b>\nনিচের কোন থানার বিটিএস তালিকা দেখতে চান?",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

# ২. নির্বাচিত থানার বিটিএস লিস্ট (পেজিনেশন সহ)
@router.callback_query(F.data.startswith("btsthana:"))
async def list_bts_by_thana(callback: CallbackQuery):
    # ফরম্যাট: btsthana:house_id:thana_name:offset
    parts = callback.data.split(":")
    house_id = int(parts[1])
    thana_name = parts[2]
    offset = int(parts[3]) if len(parts) > 3 else 0
    limit = 5

    async with async_session() as session:
        # ফিল্টার্ড ডাটা সংগ্রহ
        query = select(BTS).where(BTS.house_id == house_id, BTS.thana_bn == thana_name)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        
        res = await session.execute(query.order_by(BTS.bts_code).limit(limit).offset(offset))
        items = res.scalars().all()

        # কিবোর্ডে এখন থানা নামও পাঠাতে হবে যাতে নেক্সট পেজ কাজ করে
        kb = get_bts_pagination_kb(items, offset, total, house_id, thana_name)
        
        text = f"📋 <b>থানা: {thana_name}</b>\nমোট বিটিএস: {bn_num(total)} টি"
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ==========================================
# ৪. প্রোফাইল ভিউ এবং ক্যাটাগরি এডিট
# ==========================================
@router.callback_query(F.data.startswith("bts_view_"))
async def view_bts_profile(callback: CallbackQuery, state: FSMContext, permissions: list):
    await state.clear()

    bts_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        b = await session.get(BTS, bts_id)
        
        builder = InlineKeyboardBuilder()
        if "edit_bts" in permissions: builder.button(text="✏️ তথ্য এডিট", callback_data=f"bts_edit_cats_{b.id}")
        
        if "delete_bts" in permissions: builder.button(text="🗑 ডিলিট", callback_data=f"bts_del_conf_{b.id}")
        builder.button(text="🔙 লিস্টে ফিরুন", callback_data=f"bts_list_{b.house_id}_0")

        await callback.message.edit_text(get_bts_full_profile_text(b), reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")

# ক্যাটাগরি ভিত্তিক এডিট মেনু
@router.callback_query(F.data.startswith("bts_edit_cats_"))
async def show_bts_edit_cats(callback: CallbackQuery):
    bts_id = int(callback.data.split("_")[3])
    builder = InlineKeyboardBuilder()

    # ৫টি গ্রুপে ভাগ করা হয়েছে # এখানে বিভাজক হিসেবে ':' ব্যবহার করা হয়েছে যাতে আন্ডারস্কোর নিয়ে সমস্যা না হয়
    cats = [
        ("🆔 পরিচয়", "ident"), 
        ("🌍 অবস্থান (EN)", "loc_en"), 
        ("📍 অবস্থান (BN)", "loc_bn"), 
        ("🌐 নেটওয়ার্ক ও ঠিকানা", "net_addr"), 
        ("📅 এয়ার ডেট", "on_air")
    ]
    for label, key in cats:
        builder.button(text=label, callback_data=f"bts_ecat:{key}:{bts_id}")
    
    builder.button(text="🔙 প্রোফাইলে ফিরুন", callback_data=f"bts_view_{bts_id}")
    builder.adjust(1)
    await callback.message.edit_text("কোন বিভাগের তথ্য এডিট করবেন?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("bts_ecat:"))
async def show_bts_fields(callback: CallbackQuery):
    parts = callback.data.split(":")
    cat = parts[1]
    bts_id = int(parts[2])
    
    # সকল ২৭টি কলামের ম্যাপিং ✅
    fields_map = {
        "ident": [
            ("Site ID", "site_id"), ("BTS Code", "bts_code"), 
            ("Site Type", "site_type"), ("Priority", "priority"), 
            ("Distro Code", "distributor_code")
        ],
        "loc_en": [
            ("Thana", "thana"), ("District", "district"), 
            ("Division", "division"), ("Cluster", "cluster"), ("Region", "region")
        ],
        "loc_bn": [
            ("থানা (বাংলা)", "thana_bn"), ("জেলা (বাংলা)", "district_bn"), 
            ("বিভাগ (বাংলা)", "division_bn"), ("ক্লাস্টার (বাংলা)", "cluster_bn"), ("রিজিয়ন (বাংলা)", "region_bn")
        ],
        "net_addr": [
            ("Network Mode", "network_mode"), ("Urban/Rural", "urban_rural"), 
            ("Archetype", "archetype"), ("Market", "market"), 
            ("Short Address", "short_address"), ("Address EN", "address"), 
            ("Address BN", "address_bn"), ("Longitude", "longitude"), ("Latitude", "latitude")
        ],
        "on_air": [
            ("2G On-Air", "onair_date_2g"), ("3G On-Air", "onair_date_3g"), ("4G On-Air", "onair_date_4g")
        ]
    }
    
    builder = InlineKeyboardBuilder()
    for label, field in fields_map.get(cat, []):
        builder.button(text=label, callback_data=f"bts_fld:{field}:{bts_id}")
    
    builder.button(text="🔙 ক্যাটাগরি", callback_data=f"bts_edit_cats_{bts_id}")
    builder.adjust(2)
    await callback.message.edit_text("নির্দিষ্ট ফিল্ড নির্বাচন করুন:", reply_markup=builder.as_markup())

# ==========================================
# ৫. ইনপুট এবং সেভ লজিক
# ==========================================
@router.callback_query(F.data.startswith("bts_fld:"))
async def start_bts_edit_input(callback: CallbackQuery, state: FSMContext):
    _, field, bts_id = callback.data.split(":")
    async with async_session() as session:
        b = await session.get(BTS, int(bts_id))

        # বর্তমান ভ্যালু সংগ্রহ এবং কপি করার উপযোগী করা
        val = getattr(b, field)
        curr = f"<code>{val}</code>" if val and str(val).lower() != 'nan' else "<i>(খালি)</i>"

        await state.update_data(edit_bts_id=b.id, edit_field=field)

        # ১. বাতিল করার বাটন তৈরি ✅
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ বাতিল করুন", callback_data=f"bts_view_{bts_id}")
        builder.adjust(1)

        # parse_mode="HTML" যুক্ত করা হয়েছে যাতে ট্যাগগুলো কাজ করে ✅
        text = (
            f"📝 <b>{field.upper().replace('_', ' ')}</b> পরিবর্তন\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 বর্তমান তথ্য: {curr}\n\n"
            f"👉 নতুন তথ্যটি লিখে পাঠান (কপি করতে উপরের টেক্সটে ক্লিক করুন):"
        )

        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.set_state(BTSStates.edit_value)
    await callback.answer()

@router.message(BTSStates.edit_value)
async def save_bts_edit(message: Message, state: FSMContext, permissions: list):
    data = await state.get_data()
    async with async_session() as session:
        b = await session.get(BTS, data['edit_bts_id'])
        setattr(b, data['edit_field'], message.text.strip())
        await session.commit()
        await session.refresh(b)
        await message.answer("✅ তথ্য আপডেট সফল!")
        # স্টেট ক্লিয়ার না করে শুধু ইনপুট প্রসেস বন্ধ (হাউজ আইডি রক্ষার জন্য)
        await state.set_state(None)
        # পুনরায় প্রোফাইল দেখানো
        builder = InlineKeyboardBuilder().button(text="📋 লিস্টে ফিরুন", callback_data=f"bts_list_{b.house_id}_0").adjust(1)
        await message.answer(get_bts_full_profile_text(b), reply_markup=builder.as_markup(), parse_mode="HTML")

# ==========================================
# ৬. এক্সেল আপলোড (লাইভ প্রগ্রেস)
# ==========================================
@router.callback_query(F.data == "bts_upload_start")
async def bts_upload_trigger(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📁 বিটিএস লিস্ট এক্সেল (.xlsx) ফাইলটি পাঠান।")
    await state.set_state(BTSStates.waiting_for_excel)
    await callback.answer()

# এক্সেল আপলোড শেষে রিডাইরেক্ট লজিক ✅ ---
@router.message(BTSStates.waiting_for_excel, F.document)
async def handle_bts_excel(message: Message, state: FSMContext):
    data = await state.get_data()
    h_id = data.get('selected_house_id')
    if not h_id: return await message.answer("❌ সেশন এরর! হাউজ পুনরায় সিলেক্ট করুন।")

    file_path = f"temp_bts_{message.from_user.id}.xlsx"
    wait_msg = await message.answer("⏳ ফাইল প্রসেস শুরু হচ্ছে...")
    
    try:
        await message.bot.download(message.document, destination=file_path)
        
        async def progress(text): 
            try: await wait_msg.edit_text(text)
            except: pass
        
        count, err = await process_bts_excel(file_path, h_id, progress)
        
        if err:
            await wait_msg.edit_text(f"❌ এরর: {err}")
        else:
            # সফল হলে সাকসেস মেসেজ দিয়ে ৩ সেকেন্ড পর লিস্ট লোড করবে ✅
            await wait_msg.edit_text(f"✅ সফল! {bn_num(count)}টি বিটিএস আপডেট হয়েছে।")
            await asyncio.sleep(3)
            
            # সরাসরি লিস্ট লোড করার লজিক
            async with async_session() as session:
                total = await session.scalar(select(func.count(BTS.id)).where(BTS.house_id == h_id))
                res = await session.execute(select(BTS).where(BTS.house_id == h_id).limit(PAGE_LIMIT))
                items = res.scalars().all()
                total_pages = (total + PAGE_LIMIT - 1) // PAGE_LIMIT
                
                from app.Views.keyboards.inline import get_bts_pagination_kb
                kb = get_bts_pagination_kb(items, 1, total_pages, h_id)
                
                await wait_msg.edit_text(f"📋 **সদ্য আপলোড হওয়া বিটিএস তালিকা** (মোট: {bn_num(total)}):", reply_markup=kb)

    except Exception as e:
        await wait_msg.edit_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        await state.clear()

# হাউজ পরিবর্তন
@router.callback_query(F.data == "bts_change_house")
async def bts_change_house(callback: CallbackQuery, state: FSMContext, permissions: list):
    await state.clear()
    user_id = callback.from_user.id # callback.from_user ব্যবহার করতে হবে ✅

    async with async_session() as session:
        # সুপার এডমিন চেক
        if int(user_id) == int(SUPER_ADMIN_ID):
            houses = (await session.execute(select(House))).scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_id)
            )).scalar_one_or_none()
            houses = user.houses if user else []

        if not houses:
            return await callback.answer("❌ কোনো হাউজ যুক্ত নেই।", show_alert=True)

        builder = InlineKeyboardBuilder()
        for h in houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"bts_hsel_{h.id}")
        
        await callback.message.edit_text("📡 **বিটিএস ম্যানেজমেন্ট**\nহাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())
    await callback.answer()

# সার্চ হ্যান্ডেলার্স

@router.callback_query(F.data == "bts_search_start")
async def start_bts_search(callback: CallbackQuery, state: FSMContext):
    """ইউজার যখন সার্চ বাটনে ক্লিক করবে"""
    # বর্তমানে সিলেক্ট করা হাউজ আইডি সংগ্রহ
    data = await state.get_data()
    h_id = data.get('selected_house_id')
    
    if not h_id:
        return await callback.answer("❌ আগে হাউজ সিলেক্ট করুন।", show_alert=True)

    await callback.message.answer(
        "🔍 <b>বিটিএস সার্চ</b>\n\nবিটিএস এর <b>কোড (BTS Code)</b>, <b>সাইট আইডি (Site ID)</b> অথবা <b>ঠিকানা</b> লিখে পাঠান:",
        parse_mode="HTML"
    )
    await state.set_state(BTSStates.search_query)
    await callback.answer()

@router.message(BTSStates.search_query)
async def process_bts_search(message: Message, state: FSMContext):
    """স্মার্ট সার্চ: ইউনিকোড নরমালাইজেশন সহ ✅"""
    
    # ১. ইনপুট নরমালাইজ করা (NFC ফরম্যাটে)
    # এটি টাইপ করা এবং কপি করা উভয় টেক্সটকে একই ইউনিকোড কোডে রূপান্তর করবে
    raw_query = message.text.strip()
    query = unicodedata.normalize('NFC', raw_query)
    
    # ২. বাড়তি সতর্কতা: জিরো উইডথ ক্যারেক্টার রিমুভ (কিবোর্ডের অদৃশ্য অক্ষর)
    query = query.replace('\u200d', '').replace('\u200c', '')

    data = await state.get_data()
    house_id = data.get('selected_house_id')

    if len(query) < 2:
        return await message.answer("⚠️ অন্তত ২ অক্ষরের নাম বা কোড লিখুন।")

    async with async_session() as session:
        # ৩. স্মার্ট প্যাটার্ন তৈরি
        search_pattern = f"%{query}%"

        res = await session.execute(
            select(BTS).where(
                BTS.house_id == house_id,
                or_(
                    BTS.bts_code.ilike(search_pattern),
                    BTS.site_id.ilike(search_pattern),
                    BTS.address.ilike(search_pattern),
                    BTS.address_bn.ilike(search_pattern),
                    BTS.thana.ilike(search_pattern),
                    BTS.thana_bn.ilike(search_pattern)
                )
            ).limit(10)
        )
        results = res.scalars().all()

        if not results:
            # যদি রেজাল্ট না পাওয়া যায়, তবে NFD ফরম্যাটে একবার ট্রাই করা (অতিরিক্ত নিরাপত্তা)
            query_alt = unicodedata.normalize('NFD', query)
            search_pattern_alt = f"%{query_alt}%"
            res_alt = await session.execute(
                select(BTS).where(BTS.house_id == house_id, BTS.thana_bn.ilike(search_pattern_alt))
            )
            results = res_alt.scalars().all()

        if not results:
            return await message.answer(f"❌ '{raw_query}' সম্পর্কিত কোনো বিটিএস পাওয়া যায়নি।")

        # বাকি বাটন জেনারেশন লজিক (আগের মতই থাকবে)...
        builder = InlineKeyboardBuilder()
        for b in results:
            addr = b.short_address if b.short_address else "N/A"
            builder.button(text=f"📡 {b.bts_code} ({addr})", callback_data=f"bts_view_{b.id}")
        
        builder.button(text="🔍 নতুন সার্চ", callback_data="bts_search_start")
        builder.button(text="🔙 মেনু", callback_data=f"bts_hsel_{house_id}")
        builder.adjust(1)

        await message.answer(
            f"✅ <b>সার্চ রেজাল্ট:</b> ({bn_num(len(results))} টি পাওয়া গেছে)",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    await state.set_state(None)

# --- ২. স্যাম্পল ডাউনলোড লজিক (সংশোধিত) ✅ ---
@router.callback_query(F.data == "bts_sample_dl")
async def download_bts_sample_file(callback: CallbackQuery):
    """ইউজারকে বিটিএস স্যাম্পল এক্সেল ফাইল পাঠাবে"""
    
    # ফাইলের নাম নির্ধারণ
    file_path = "BTS_List_Template.xlsx"
    
    try:
        # সার্ভিস থেকে স্যাম্পল ফাইল জেনারেট করার ফাংশন কল
        
        await generate_bts_sample(file_path)
        
        # ফাইলটি টেলিগ্রামে পাঠানো
        await callback.message.answer_document(
            document=FSInputFile(file_path),
            caption=(
                "📡 <b>বিটিএস লিস্ট টেমপ্লেট</b>\n\n"
                "নিচের ফাইলটি ডাউনলোড করে সকল তথ্য (২৭টি কলাম) সঠিক ফরম্যাটে পূরণ করুন। "
                "এরপর '📤 এক্সেল আপলোড' বাটনে গিয়ে ফাইলটি আপলোড দিন।"
            ),
            parse_mode="HTML"
        )
        
        # পাঠানো শেষ হলে পিসি থেকে টেম্পোরারি ফাইলটি মুছে ফেলা
        if os.path.exists(file_path):
            os.remove(file_path)
            
        await callback.answer("ফাইল পাঠানো হয়েছে")

    except Exception as e:
        logger.error(f"❌ স্যাম্পল ফাইল পাঠাতে সমস্যা: {str(e)}")
        await callback.answer(f"❌ এরর: ফাইলটি তৈরি করা যায়নি।", show_alert=True)


# ==========================================
# ৭. ডিলিট কনফার্মেশন এবং ডিলিট লজিক
# ==========================================
@router.callback_query(F.data.startswith("bts_del_conf_"), flags={"permission": "delete_bts"})
async def confirm_bts_delete(callback: CallbackQuery):
    bts_id = int(callback.data.split("_")[3])
    
    async with async_session() as session:
        # ডাটাবেজ থেকে বিটিএসটি খুঁজে বের করা যাতে নাম/কোড দেখানো যায়
        bts = await session.get(BTS, bts_id)
        if not bts:
            return await callback.answer("❌ বিটিএস পাওয়া যায়নি।", show_alert=True)
        
        bts_info = f"{bts.bts_code} ({bts.short_address or 'ঠিকানা নেই'})"

    # বাটন তৈরি
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ হ্যাঁ, নিশ্চিত ডিলিট", callback_data=f"bts_final_del_{bts_id}")
    builder.button(text="❌ না, বাতিল করুন", callback_data=f"bts_view_{bts_id}")
    builder.adjust(1)

    text = (
        f"⚠️ <b>সতর্কতা: বিটিএস ডিলিট</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"আপনি কি নিশ্চিতভাবে বিটিএস: <b>{bts_info}</b>-কে ডাটাবেজ থেকে মুছে ফেলতে চান?\n\n"
        f"<i>এটি ডিলিট করলে আর ফিরিয়ে আনা যাবে না।</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# --- ৭. চূড়ান্ত ডিলিট লজিক ✅ ---
@router.callback_query(F.data.startswith("bts_final_del_"), flags={"permission": "delete_bts"})
async def final_bts_delete(callback: CallbackQuery):
    bts_id = int(callback.data.split("_")[3])
    
    async with async_session() as session:
        bts = await session.get(BTS, bts_id)
        
        if bts:
            house_id = bts.house_id
            bts_code = bts.bts_code
            
            # ডিলিট অপারেশন
            await session.delete(bts)
            await session.commit()
            
            # ইউজারের জন্য নোটিফিকেশন
            await callback.answer(f"🗑 বিটিএস {bts_code} ডিলিট করা হয়েছে।", show_alert=True)
            
            # ডিলিট হওয়ার পর স্বয়ংক্রিয়ভাবে লিস্টে ফেরত নিয়ে যাবে
            # আমরা এখানে dummpy সেশন ডাটা পাঠিয়ে লিস্ট ফাংশন কল করতে পারি
            await callback.message.delete() # বর্তমান সতর্কবার্তা মুছে ফেলা
            await render_bts_dashboard(callback.message, house_id, permissions=[]) # মেইন ড্যাশবোর্ডে ফেরত
        else:
            await callback.answer("❌ বিটিএস ইতিমধ্যে মুছে ফেলা হয়েছে।")