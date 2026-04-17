import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, not_
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Models.house import House
from app.Models.live_activation import LiveActivation
from app.Models.field_force import FieldForce
from app.Models.ga_filter import GAProductFilter, GARetailerFilter
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID
from app.Views.keyboards.reply import get_reports_mgmt_menu, get_admin_main_menu

logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# ১. এন্ট্রি পয়েন্ট (রিপ্লাই কিবোর্ড থেকে)
# ==========================================

@router.message(F.text == "📊 রিপোর্টস", flags={"permission": "report_access"})
async def show_reports_sub_menu(message: Message, permissions: list):
    await message.answer(
        "📊 **রিপোর্ট মডিউল**\nনিচের বাটন থেকে কাঙ্ক্ষিত রিপোর্টটি নির্বাচন করুন:",
        reply_markup=get_reports_mgmt_menu(permissions)
    )

@router.message(F.text == "📡 জিএ লাইভ", flags={"permission": "view_ga_live"})
async def handle_ga_live_initial(message: Message):
    """এটিই একমাত্র ফাংশন যা নতুন মেসেজ পাঠাবে ✅"""
    await handle_ga_logic_core(message, message.from_user.id, edit=False)

# ==========================================
# ২. কোর লজিক (নতুন পাঠানো বা এডিট করা উভয়ের জন্য)
# ==========================================

async def handle_ga_logic_core(message: Message, user_tg_id: int, edit: bool = False):
    from config.settings import SUPER_ADMIN_ID
    is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

    async with async_session() as session:
        target_houses = []
        if is_super_admin:
            target_houses = (await session.execute(select(House))).scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )).scalar_one_or_none()
            if user: target_houses = user.houses

        if not target_houses:
            text = "❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।"
            return await message.edit_text(text) if edit else await message.answer(text)

        # ১টি হাউজ থাকলে সরাসরি রিপোর্ট
        if len(target_houses) == 1:
            await send_ga_detailed_report(message, target_houses[0], edit=edit)
            return

        # একাধিক হাউজ থাকলে সিলেকশন বাটন
        builder = InlineKeyboardBuilder()
        for h in target_houses: 
            builder.button(text=f"🏢 {h.name}", callback_data=f"ga_hsel_{h.id}")
        builder.adjust(2)
        
        text = "কোন হাউজের **জিএ লাইভ রিপোর্ট** দেখতে চান?"
        
        if edit:
            await message.edit_text(text, reply_markup=builder.as_markup())
        else:
            await message.answer(text, reply_markup=builder.as_markup())

# ==========================================
# ৩. কলব্যাক হ্যান্ডেলার্স (সবগুলো এখন এডিট করবে)
# ==========================================

@router.callback_query(F.data.startswith("ga_hsel_"))
async def process_ga_house_select(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        house = await session.get(House, house_id)
        if house: 
            # রিপোর্ট দেখানোর সময় edit=True দেওয়া হয়েছে যাতে মেসেজ এডিট হয় ✅
            await send_ga_detailed_report(callback.message, house, edit=True)
    await callback.answer()

@router.callback_query(F.data == "ga_live_main")
async def handle_ga_back_inline(callback: CallbackQuery):
    """রিপোর্ট থেকে মেইন লিস্টে ফিরে আসা (মেসেজ এডিট করে) ✅"""
    await handle_ga_logic_core(callback.message, callback.from_user.id, edit=True)
    await callback.answer()

# ==========================================
# ৪. মেইন রিপোর্ট জেনারেশন ও রেন্ডারিং ✅
# ==========================================

async def send_ga_detailed_report(message: Message, house: House, edit: bool = False):
    async with async_session() as session:
        # ১. ফিল্টার ও ডাটা লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()
        r_filters = (await session.execute(select(GARetailerFilter.keyword).where(GARetailerFilter.house_id == house.id))).scalars().all()
        excluded_keywords = [k.upper() for k in r_filters]

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()
        house_total = len(activations)
        
        act_map = {}
        for a in activations:
            code = str(a.retailer_code).replace("'", "").strip().upper()
            act_map[code] = act_map.get(code, 0) + 1

        ff_res = await session.execute(
            select(FieldForce).options(selectinload(FieldForce.retailers))
            .where(FieldForce.house_id == house.id, func.lower(FieldForce.status) == 'active')
        )
        field_forces = ff_res.scalars().all()

        sr_active_list = [] # যাদের জিএ আছে
        sr_zero_list = []   # যাদের জিএ শূন্য ✅
        bp_final_data = []
        
        for ff in field_forces:
            own_code = str(ff.assisted_retailer_code).replace("'", "").strip().upper() if ff.assisted_retailer_code else ""
            own_ga = act_map.get(own_code, 0)
            ff_type = str(ff.type).strip().upper()

            if ff_type in ['SR', 'RSO']:
                itop_suffix = str(ff.itop_number)[-3:] if ff.itop_number else "N/A"
                market_ga = 0
                if ff.retailers:
                    for r in ff.retailers:
                        r_code = str(r.retailer_code).replace("'", "").strip().upper()
                        is_excluded = any(kw in r_code or kw in str(r.name).upper() for kw in excluded_keywords)
                        if r_code != own_code and not is_excluded:
                            market_ga += act_map.get(r_code, 0)
                
                total_ga = own_ga + market_ga
                sr_item = {"name": ff.name, "suffix": itop_suffix, "own": own_ga, "market": market_ga, "total": total_ga}
                
                # লজিক: টোটাল জিএ অনুযায়ী লিস্টে ভাগ করা ✅
                if total_ga > 0:
                    sr_active_list.append(sr_item)
                else:
                    sr_zero_list.append(sr_item)
            
            elif ff_type == 'BP':
                pool_suffix = str(ff.pool_number)[-3:] if ff.pool_number else "N/A"
                bp_final_data.append({"name": ff.name, "suffix": pool_suffix, "count": own_ga})
                 

        # ২. রিপোর্ট টেক্সট ফরম্যাটিং
        report_time = datetime.now().strftime("%d %b’%y – %I:%M:%S %p")
        text = f"🏢 হাউজ: <b>{house.name}</b>\n"
        text += (
            f"📊 <b>GA Live Report</b>\n"
            f"{report_time}\n\n"
        )
        
        # SR / RSO Section
        text += "🏠 <b>এস আর রিপোর্ট</b>\n"
        text += "━━━━━━━━━━━\n"
        sr_total_count = 0
        if sr_active_list:
            for i, sr in enumerate(sr_active_list, 1):
                sr_total_count += sr['total']
                text += f"{bn_num(i)} <b>{sr['name']}</b> ({sr['suffix']})\n"
                text += f"┗ নিজেরঃ {bn_num(sr['own'])}টি\n"
                text += f"┗ মার্কেটঃ {bn_num(sr['market'])}টি\n"
                text += f"┗ মোটঃ <b>{bn_num(sr['total'])}টি</b>\n\n"
        else:
            text += "<i>আজকে কারো জিএ হয়নি</i>\n\n"
        text += f"🏁 <b>এসআর সর্বমোটঃ {bn_num(sr_total_count)}টি</b>\n\n"
        
        # SR Zero GA Section (যাদের আজকে কাজ হয়নি) ✅
        if sr_zero_list:
            text += "--------------------------\n"
            for i, sr in enumerate(sr_zero_list, 1):
                text += f"{bn_num(i)} {sr['name']} ({sr['suffix']})\n"
            text += "আজকে এদের কোন জিএ হয়নি।\n\n"



        # BP Section
        text += "👷‍♂️ <b>বিপি রিপোর্ট</b>\n"
        text += "━━━━━━━━━━━━━\n"
        bp_total_count = 0
        if bp_final_data:
            for i, bp in enumerate(bp_final_data, 1):
                bp_total_count += bp['count']
                text += f"{bn_num(i)} <b>{bp['name']}</b> ({bp['suffix']}), {bn_num(bp['count'])}টি\n"
        else:
            text += "<i>কোনো বিপি ডাটা পাওয়া যায়নি</i>\n"
        text += f"\n🏁 <b>বিপি সর্বমোটঃ {bn_num(bp_total_count)}টি</b>\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🔥 <b>হাউজের সর্বমোট জিএঃ {bn_num(house_total)}টি</b>\n"
        
        # ৫ মিনিট পর পর আপডেটের তথ্য নোট হিসেবে যোগ করা হলো
        text += "🕒 <i>জিএ রিপোর্টটি প্রতি ৫ মিনিট পর পর স্বয়ংক্রিয়ভাবে আপডেট হয়।</i>"

        # ৩. বাটন (রিফ্রেশ এবং ব্যাক)
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ করুন", callback_data=f"ga_hsel_{house.id}")
        builder.button(text="🔙 হাউজ লিস্ট", callback_data="ga_live_main")
        builder.adjust(2)

        # ৪. স্মার্ট আপডেট ✅
        if edit:
            try:
                await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except:
                # যদি ডাটা এক হয় (কিছুই না বদলায়), তবে এডিট এরর দিবে, তখন আমরা জাস্ট অ্যানসার করবো
                await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")