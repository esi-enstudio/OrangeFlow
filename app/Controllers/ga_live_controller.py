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
from app.Models.retailer import Retailer
from app.Models.ga_filter import GAProductFilter, GARetailerFilter
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

# --- ১. রিপোর্ট মেনু ---
@router.message(F.text == "📊 রিপোর্টস", flags={"permission": "report_access"})
async def show_reports_menu(message: Message, permissions: list):
    builder = InlineKeyboardBuilder()
    if "view_ga_live" in permissions:
        builder.button(text="📡 জিএ লাইভ", callback_data="ga_live_main")
    builder.adjust(1)
    await message.answer("📊 **রিপোর্ট মডিউল**", reply_markup=builder.as_markup())

# --- ২. হাউজ চেক লজিক ---
@router.callback_query(F.data == "ga_live_main", flags={"permission": "view_ga_live"})
async def handle_ga_live_request(callback: CallbackQuery):
    user_tg_id = callback.from_user.id
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
            return await callback.message.answer("❌ কোনো হাউজ যুক্ত নেই।")

        if len(target_houses) == 1:
            await send_ga_detailed_report(callback.message, target_houses[0])
        else:
            builder = InlineKeyboardBuilder()
            for h in target_houses: 
                builder.button(text=f"🏢 {h.name}", callback_data=f"ga_hsel_{h.id}")
            builder.adjust(2)
            await callback.message.edit_text("কোন হাউজের রিপোর্ট দেখতে চান?", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("ga_hsel_"))
async def process_ga_house_select(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        house = await session.get(House, house_id)
        if house: await send_ga_detailed_report(callback.message, house)
    await callback.answer()

# --- ৩. মেইন রিপোর্ট জেনারেশন লজিক (সংশোধিত ও ক্লিন) ✅ ---
async def send_ga_detailed_report(message: Message, house: House):
    """ফিল্টার এবং গ্রুপিং অনুযায়ী বিস্তারিত জিএ রিপোর্ট তৈরি (চূড়ান্ত ফিক্স) ✅"""
    async with async_session() as session:
        # ১. ফিল্টার লোড করা
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()
        r_filters = (await session.execute(select(GARetailerFilter.keyword).where(GARetailerFilter.house_id == house.id))).scalars().all()
        excluded_keywords = [k.upper() for k in r_filters]

        # ২. আজকের লাইভ এক্টিভেশন ডাটা ফেচ
        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()
        house_total = len(activations)
        
        # রিটেইলার কোড অনুযায়ী কাউন্ট ম্যাপ (সিঙ্গেল কোট রিমুভ করে)
        act_map = {}
        for a in activations:
            code = str(a.retailer_code).replace("'", "").strip().upper()
            act_map[code] = act_map.get(code, 0) + 1

        # ৩. ফিল্ড ফোর্স লোড করা (টাইপ নির্বিশেষে এক্টিভ মেম্বার)
        ff_res = await session.execute(
            select(FieldForce).options(selectinload(FieldForce.retailers))
            .where(FieldForce.house_id == house.id, func.lower(FieldForce.status) == 'active')
        )
        field_forces = ff_res.scalars().all()

        # ক্যালকুলেশন শুরু
        sr_final_data = []
        bp_final_data = []
        
        for ff in field_forces:
            # আরএসও-র নিজের কোড চিহ্নিত করা (Assisted Code থেকে)
            own_code = str(ff.assisted_retailer_code).replace("'", "").strip().upper()
            own_ga = act_map.get(own_code, 0)
            
            # আইটপ নাম্বারের শেষ ৩ সংখ্যা (উদা: 019...001 থেকে 001) ✅
            itop_suffix = str(ff.itop_number)[-3:] if ff.itop_number else "N/A"

            if ff.type in ['SR', 'RSO']:
                market_ga = 0
                for r in ff.retailers:
                    r_code = str(r.retailer_code).replace("'", "").strip().upper()
                    # শর্ত: যদি এটি আরএসও-র নিজের কোড না হয়, তবেই মার্কেটে কাউন্ট হবে
                    if r_code != own_code:
                        market_ga += act_map.get(r_code, 0)
                
                sr_final_data.append({
                    "name": ff.name,
                    "suffix": itop_suffix,
                    "own": own_ga,
                    "market": market_ga,
                    "total": own_ga + market_ga
                })
            
            elif ff.type == 'BP':
                bp_final_data.append({
                    "name": ff.name,
                    "suffix": itop_suffix,
                    "count": own_ga
                })


        # # --- ৪. রিপোর্ট টেক্সট ফরম্যাটিং (HTML) ---
        report_time = datetime.now().strftime("%d %b’%y – %I:%M:%S %p")
        text = f"📊 <b>GA Live Report</b> ({report_time})\n\n"

        # SR / RSO Section
        text += "🏠 <b>এস আর রিপোর্ট</b>\n"
        text += "━━━━━━━━━━━━━\n"
        sr_total_count = 0
        if sr_final_data:
            for i, sr in enumerate(sr_final_data, 1):
                sr_total_count += sr['total']
                # নাম (আইটপ নাম্বারের শেষ ৩ সংখ্যা)
                text += f"{bn_num(i)} <b>{sr['name']}</b> ({sr['suffix']})\n"
                # আপনার দেওয়া নতুন ফরম্যাট: ┗ নিজেরঃ ০টি স্টাইলে
                text += f"┗ নিজেরঃ {bn_num(sr['own'])}টি\n"
                text += f"┗ মার্কেটঃ {bn_num(sr['market'])}টি\n"
                text += f"┗ মোটঃ <b>{bn_num(sr['total'])}টি</b>\n\n"
        else:
            text += "<i>কোনো এসআর ডাটা পাওয়া যায়নি</i>\n\n"
        
        text += f"🏁 <b>এসআর সর্বমোটঃ {bn_num(sr_total_count)}টি</b>\n\n"

        # BP Section
        text += "👷‍♂️ <b>বিপি রিপোর্ট</b>\n"
        text += "━━━━━━━━━━━━━\n"
        bp_total_count = 0
        if bp_final_data:
            for i, bp in enumerate(bp_final_data, 1):
                bp_total_count += bp['count']
                # বিপি নাম (আইটপ নাম্বারের শেষ ৩ সংখ্যা)
                text += f"{bn_num(i)} <b>{bp['name']}</b> ({bp['suffix']}), {bn_num(bp['count'])}টি\n"
        else:
            text += "<i>কোনো বিপি ডাটা পাওয়া যায়নি</i>\n"
            
        text += f"\n🏁 <b>বিপি সর্বমোটঃ {bn_num(bp_total_count)}টি</b>\n"
        
        # হাউজের সর্বমোট
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🔥 <b>হাউজের সর্বমোট জিএঃ {bn_num(house_total)}টি</b>"

        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ", callback_data=f"ga_hsel_{house.id}")
        builder.button(text="🔙 ব্যাকে যান", callback_data="ga_live_main")
        builder.adjust(2)

        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")