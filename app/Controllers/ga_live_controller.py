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
from app.Models.mela import Mela, MelaAssignment
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID
from app.Views.keyboards.reply import get_reports_mgmt_menu

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
            await send_ga_detailed_report(message, target_houses[0], user_id=user_tg_id, edit=edit)
            return

        # একাধিক হাউজ থাকলে সিলেকশন বাটন
        builder = InlineKeyboardBuilder()
        for h in target_houses: 
            builder.button(text=f"🏢 {h.display_name}", callback_data=f"ga_hsel_{h.id}")
        builder.adjust(1)
        
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
            await send_ga_detailed_report(callback.message, house, user_id=callback.from_user.id, edit=True)
    await callback.answer()

@router.callback_query(F.data == "ga_live_main")
async def handle_ga_back_inline(callback: CallbackQuery):
    """রিপোর্ট থেকে মেইন লিস্টে ফিরে আসা (মেসেজ এডিট করে) ✅"""
    await handle_ga_logic_core(callback.message, callback.from_user.id, edit=True)
    await callback.answer()

# ==========================================
# ৪. মেইন রিপোর্ট জেনারেশন ও রেন্ডারিং ✅
# ==========================================

async def send_ga_detailed_report(message: Message, house: House, user_id: int, edit: bool = False):
    async with async_session() as session:
        # ১. আজকের তারিখ নির্ধারণ (DMS এক্সেল ফরম্যাট অনুযায়ী: 18-Apr-2026) ✅
        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y") 
        # দ্রষ্টব্য: যদি আপনার ডাটাবেজে তারিখ '18-04-2026' ফরম্যাটে থাকে তবে "%d-%m-%Y" দিবেন
        
        # ১. ফিল্টার ও ডাটা লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()
        r_filters = (await session.execute(select(GARetailerFilter.keyword).where(GARetailerFilter.house_id == house.id))).scalars().all()
        excluded_keywords = [k.upper() for k in r_filters]

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
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
        cc_final_data = []
        
        # --- এ হাউজের সকল বিপি (BP) কোডগুলো সংগ্রহ করা (অটো-ফিল্টারের জন্য) ---
        bp_codes_res = await session.execute(
            select(FieldForce.assisted_retailer_code)
            .where(FieldForce.house_id == house.id, FieldForce.type == 'BP')
        )
        # সকল বিপির কোড একটি সেটে রাখা হলো যাতে দ্রুত সার্চ করা যায়
        all_bp_codes = {str(c[0]).replace("'", "").strip().upper() for c in bp_codes_res.all() if c[0]}
        
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
                        
                        # --- স্মার্ট মার্কেট ফিল্টার লজিক ✅ ---
                        # ক. চেক ১: এটি কি আরএসও-র নিজের কোড?
                        is_own_code = (r_code == own_code)
                        
                        # খ. চেক ২: এটি কি কোনো বিপি (BP) এর ব্যক্তিগত কোড? (অটো-ম্যাচিং)
                        is_bp_code = (r_code in all_bp_codes)
                        
                        # গ. চেক ৩: এটি কি এডমিনের দেওয়া কাস্টম ফিল্টার কিওয়ার্ড/কোড এর সাথে মিলে?
                        is_manual_excluded = any(kw in r_code or kw in str(r.name).upper() for kw in excluded_keywords)
                        
                        # কোনো শর্ত মিললে সেটি মার্কেটে কাউন্ট হবে না
                        if not is_own_code and not is_bp_code and not is_manual_excluded:
                            market_ga += act_map.get(r_code, 0)
                
                total_ga = own_ga + market_ga
                sr_item = {"name": ff.name, "suffix": itop_suffix, "own": own_ga, "market": market_ga, "total": total_ga}
                
                # লজিক: টোটাল জিএ অনুযায়ী লিস্টে ভাগ করা ✅
                if total_ga > 0:
                    sr_active_list.append(sr_item)
                else:
                    sr_zero_list.append(sr_item)
            
            # বিপি লজিক
            elif ff_type == 'BP':
                pool_suffix = str(ff.pool_number)[-3:] if ff.pool_number else "N/A"
                bp_final_data.append({"name": ff.name, "suffix": pool_suffix, "count": own_ga})
            
            # সিসি (CC) লজিক
            elif ff_type == 'CC':
                # সিসিদের জন্য পুল নাম্বারের শেষ ৩ ডিজিট সংগ্রহ
                pool_suffix = str(ff.pool_number)[-3:] if ff.pool_number else "N/A"
                
                cc_final_data.append({
                    "name": ff.name,
                    "suffix": pool_suffix, # এখানে আইটপ এর বদলে পুল সাফিক্স বসবে ✅
                    "count": own_ga
                })
                 

        # ২. রিপোর্ট টেক্সট ফরম্যাটিং
        report_time = datetime.now().strftime("%d %b’%y – %I:%M:%S %p")

        # রিপোর্ট হেডার
        text = f"🏢 হাউজ: <b>{house.name}</b>\n"
        text += (
            f"📊 <b>GA Live Report</b>\n"
            f"{report_time}\n\n"
        )

        # ১. এস আর রিপোর্ট (যদি এসআর থাকে তবেই দেখাবে) ✅
        if sr_active_list or sr_zero_list:
            text += "🏠 <b>এস আর রিপোর্ট</b>\n━━━━━━━━━━━\n"
            sr_grand = 0
            if sr_active_list:
                for i, sr in enumerate(sr_active_list, 1):
                    sr_grand += sr['total']
                    text += f"{bn_num(i)} <b>{sr['name']}</b> ({sr['suffix']})\n"
                    text += f"┗ নিজেরঃ {bn_num(sr['own'])}টি\n"
                    text += f"┗ মার্কেটঃ {bn_num(sr['market'])}টি\n"
                    text += f"┗ মোটঃ <b>{bn_num(sr['total'])}টি</b>\n\n"
            
            text += f"🏁 <b>এসআর সর্বমোটঃ {bn_num(sr_grand)}টি</b>\n"

            # SR Zero GA Section (যাদের আজকে কাজ হয়নি) ✅
        if sr_zero_list:
            text += "--------------------------\n"
            for i, sr in enumerate(sr_zero_list, 1):
                text += f"{bn_num(i)} {sr['name']} ({sr['suffix']})\n"
            text += "আজকে এদের কোন জিএ হয়নি।\n\n"
            

        # ২. বিপি রিপোর্ট (যদি বিপি থাকে তবেই দেখাবে) ✅
        if bp_final_data:
            text += "👷‍♂️ <b>বিপি রিপোর্ট</b>\n━━━━━━━━━━━━━\n"
            bp_grand = 0
            for i, bp in enumerate(bp_final_data, 1):
                bp_grand += bp['count']
                text += f"{bn_num(i)} <b>{bp['name']}</b> ({bp['suffix']}), {bn_num(bp['count'])}টি\n"
            
            text += f"\n🏁 <b>বিপি সর্বমোটঃ {bn_num(bp_grand)}টি</b>\n\n"


        # ৩. সিসি রিপোর্ট (যদি সিসি থাকে তবেই দেখাবে) ✅
        if cc_final_data:
            text += "🎧 <b>সিসি রিপোর্ট</b>\n━━━━━━━━━━━━━\n"
            cc_grand = 0
            for i, cc in enumerate(cc_final_data, 1):
                cc_grand += cc['count']
                text += f"{bn_num(i)} <b>{cc['name']}</b> ({cc['suffix']}), {bn_num(cc['count'])}টি\n"
            
            text += f"🏁 <b>সিসি সর্বমোটঃ {bn_num(cc_grand)}টি</b>\n\n"

        # ৪. গ্লোবাল ফুটার (হাউজের সর্বমোট)
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🔥 <b>হাউজের সর্বমোট জিএঃ {bn_num(house_total)}টি</b>\n"
        # text += "🕒 জিএ রিপোর্টটি প্রতি ৫ মিনিট পর পর স্বয়ংক্রিয়ভাবে আপডেট হয়।"

        # ৫. মেলা রিপোর্ট (যদি আজকের তারিখে মেলা থাকে)
        from datetime import date
        today_date = date.today()
        mela_report = await generate_mela_report(session, house.id, today_date)
        if mela_report:
            # text += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            text += mela_report

        # ৩. বাটন (রিফ্রেশ এবং ব্যাক)
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ করুন", callback_data=f"ga_hsel_{house.id}")

        is_super_admin = (int(user_id) == int(SUPER_ADMIN_ID))

        # ডাটাবেজ থেকে ইউজারের হাউজ সংখ্যা পুনরায় নিশ্চিত করা
        user_res = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == user_id)
        )
        user_obj = user_res.scalar_one_or_none()
        house_count = len(user_obj.houses) if user_obj and user_obj.houses else 0

        # এখন কন্ডিশনটি সবার জন্য কাজ করবে ✅
        if is_super_admin or house_count > 1:
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


async def generate_mela_report(session, house_id, today_date):
    """আজকের তারিখে মেলা থাকলে রিপোর্ট টেক্সট রিটার্ন করে, নাহলে খালি স্ট্রিং।"""
    from datetime import date
    # মেলা খুঁজুন
    mela_res = await session.execute(
        select(Mela)
        .where(Mela.house_id == house_id, Mela.activity_date == today_date)
        .options(selectinload(Mela.mela_type), selectinload(Mela.mela_activity),
                 selectinload(Mela.covered_bts), selectinload(Mela.assignments))
    )
    mela = mela_res.scalar_one_or_none()
    if not mela:
        return ""
    
    # মেলা ডিটেইল
    mela_type = mela.mela_type.name if mela.mela_type else "N/A"
    mela_activity = mela.mela_activity.name if mela.mela_activity else "N/A"
    thana = mela.thana or "N/A"
    location = mela.location or "N/A"
    
    # বিটিএস লিস্ট
    bts_lines = []
    for idx, bts in enumerate(mela.covered_bts, 1):
        bts_lines.append(f" {bn_num(idx)} {bts.bts_code}-{bts.short_address_bn or 'N/A'}")
    bts_text = "\n".join(bts_lines) if bts_lines else "কোনো বিটিএস নেই"
    
    # অংশগ্রহণকারী সংগ্রহ
    rso_assignments = [a for a in mela.assignments if a.role_type == 'RSO']
    bp_assignments = [a for a in mela.assignments if a.role_type == 'BP']
    retailer_assignments = [a for a in mela.assignments if a.role_type == 'SSO']
    
    # অ্যাক্টিভেশন গণনা
    # আজকের অ্যাক্টিভেশন থেকে retailer_code অনুযায়ী গণনা
    act_res = await session.execute(
        select(LiveActivation.retailer_code, func.count(LiveActivation.id))
        .where(LiveActivation.house_id == house_id, LiveActivation.activation_date == today_date.strftime("%d-%b-%Y"))
        .group_by(LiveActivation.retailer_code)
    )
    activation_map = {str(code).upper(): count for code, count in act_res.all()}
    
    # FieldForce ডিটেইলস ফেচ করার জন্য
    all_codes = set()
    for a in rso_assignments + bp_assignments + retailer_assignments:
        if a.retailer_code:
            all_codes.add(a.retailer_code.upper())
    
    field_force_map = {}
    if all_codes:
        ff_res = await session.execute(
            select(FieldForce)
            .where(FieldForce.assisted_retailer_code.in_(all_codes))
        )
        for ff in ff_res.scalars():
            field_force_map[ff.assisted_retailer_code.upper() if ff.assisted_retailer_code else ""] = ff
    
    # RSO রিপোর্ট - ফরম্যাট: "R591412 (366): ২টি"
    rso_lines = []
    rso_total = 0
    for idx, rso in enumerate(rso_assignments, 1):
        code = rso.retailer_code.upper()
        count = activation_map.get(code, 0)
        rso_total += count
        
        ff = field_force_map.get(code)
        if ff:
            # RSO ফরম্যাট: কোড (আইটপ/পুল): কাউন্ট
            suffix = ff.itop_number or ff.pool_number or ""
            display = f"{rso.retailer_code} ({suffix})" if suffix else rso.retailer_code
        else:
            display = rso.retailer_code
        
        rso_lines.append(f" {bn_num(idx)} {display}: {bn_num(count)}টি")
    rso_section = "\n".join(rso_lines) if rso_lines else "কোনো RSO নেই"
    
    # BP রিপোর্ট - ফরম্যাট: "Sher Ali-R591989: ৬টি"
    bp_lines = []
    bp_total = 0
    for idx, bp in enumerate(bp_assignments, 1):
        code = bp.retailer_code.upper()
        count = activation_map.get(code, 0)
        bp_total += count
        
        ff = field_force_map.get(code)
        if ff:
            # BP ফরম্যাট: নাম-কোড: কাউন্ট
            display = f"{ff.name}-{bp.retailer_code}"
        else:
            display = bp.retailer_code
        
        bp_lines.append(f" {bn_num(idx)} {display}: {bn_num(count)}টি")
    bp_section = "\n".join(bp_lines) if bp_lines else "কোনো BP নেই"
    
    # Retailer রিপোর্ট - ফরম্যাট: "Alaina Telecom (102): ০টি"
    retailer_lines = []
    retailer_total = 0
    for idx, ret in enumerate(retailer_assignments, 1):
        code = ret.retailer_code.upper()
        count = activation_map.get(code, 0)
        retailer_total += count
        
        ff = field_force_map.get(code)
        if ff:
            # Retailer ফরম্যাট: নাম (কোড): কাউন্ট
            display = f"{ff.name} ({ret.retailer_code})"
        else:
            display = ret.retailer_code
        
        retailer_lines.append(f" {bn_num(idx)} {display}: {bn_num(count)}টি")
    retailer_section = "\n".join(retailer_lines) if retailer_lines else "কোনো রিটেইলার নেই"
    
    # সর্বমোট জিএ
    total_ga = rso_total + bp_total + retailer_total
    
    # ফরম্যাটেড রিপোর্ট - ইউজারের উদাহরণ অনুযায়ী
    report = f"""
** মেলা রিপোর্ট **
---------------------------
🏗 ধরণ: {mela_type}
🎯 কাজ: {mela_activity}
🏘 থানা: {thana}
📍 লোকেশন: {location}

📡 বিটিএস কোডসমূহ:
{bts_text}

👥 অংশগ্রহণকারী মেম্বার:
🔹 আরএসও ({len(rso_assignments)} জন):
{rso_section}
-------------------------------------
মোটঃ {bn_num(rso_total)}টি

🔹 বিপি ({len(bp_assignments)} জন):
{bp_section}
------------------------------------
মোটঃ {bn_num(bp_total)}টি

🔹 রিটেইলার ({len(retailer_assignments)} জন):
{retailer_section}
-----------------------------------
মোটঃ {bn_num(retailer_total)}টি

আজকের মেলার সর্বমোট জিএঃ {bn_num(total_ga)}টি
"""
    return report