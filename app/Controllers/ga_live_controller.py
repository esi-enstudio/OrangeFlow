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
from app.Models.retailer import Retailer
from app.Models.mela import Mela, MelaAssignment
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID
from app.Views.keyboards.reply import get_reports_mgmt_menu

logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# ১. এন্ট্রি পয়েন্ট (রিপ্লাই কিবোর্ড থেকে)
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
# ২. কোর লজিক (নতুন পাঠানো বা এডিট করা উভয়ের জন্য)
# ==========================================

async def handle_ga_logic_core(message: Message, user_tg_id: int, edit: bool = False):
    is_super_admin = (int(user_tg_id) == int(SUPER_ADMIN_ID))

    async with async_session() as session:
        target_houses = []
        if is_super_admin:
            target_houses = (await session.execute(select(House).where(House.is_active == True, House.subscription_date >= datetime.now()))).scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_tg_id)
            )).scalar_one_or_none()
            if user: target_houses = [h for h in user.houses if h.is_active and h.subscription_date and h.subscription_date >= datetime.now()]

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
            # রিপোর্ট দেখানোর সময় edit=True দেওয়া হয়েছে যাতে মেসেজ এডিট হয় ✅
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
        # ১. আজকের তারিখ নির্ধারণ (DMS এক্সেল ফরম্যাট অনুযায়ী: 18-Apr-2026) ✅
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
        # সকল বিপির কোড একটি সেটে রাখা হলো যাতে দ্রুত সার্চ করা যায়
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

                        # গ. চেক ৩: এটি কি এডমিনের দেওয়া কাস্টম ফিল্টার কিওয়ার্ড/কোড এর সাথে মিলে?
                        is_manual_excluded = any(kw in r_code or kw in str(r.name).upper() for kw in excluded_keywords)

                        # কোনো শর্ত মিললে সেটি মার্কেটে কাউন্ট হবে না
                        if not is_own_code and not is_bp_code and not is_manual_excluded:
                            market_ga += act_map.get(r_code, 0)

                total_ga = own_ga + market_ga
                sr_item = {"name": ff.name, "suffix": itop_suffix, "own": own_ga, "market": market_ga, "total": total_ga}

                # লজিক: টোটাল জিএ অনুযায়ী লিস্টে ভাগ করা ✅
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
        report_time = datetime.now().strftime("%d %b'%y – %I:%M:%S %p")

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

            # SR Zero GA Section (যাদের আজকে কাজ হয়নি) ✅
        if sr_zero_list:
            text += "--------------------------\n"
            for i, sr in enumerate(sr_zero_list, 1):
                text += f"{bn_num(i)} {sr['name']} ({sr['suffix']})\n"
            text += "আজকে এদের কোন জিএ হয়নি।\n\n"


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
        # text += "🕒 জিএ রিপোর্টটি প্রতি ৫ মিনিট পর পর স্বয়ংক্রিয়ভাবে আপডেট হয়।"

        # ৫. মেলা রিপোর্ট (যদি আজকের তারিখে মেলা থাকে)
        from datetime import date
        today_date = date.today()
        mela_report = await generate_mela_report(session, house.id, today_date)
        if mela_report:
            # text += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            text += mela_report

        # ৩. বাটন (রিফ্রেশ, বিস্তারিত এবং ব্যাক)
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ করুন", callback_data=f"ga_hsel_{house.id}")
        builder.button(text="📋 বিস্তারিত", callback_data=f"ga_details_menu_{house.id}")

        is_super_admin = (int(user_id) == int(SUPER_ADMIN_ID))

        # ডাটাবেজ থেকে ইউজারের হাউজ সংখ্যা পুনরায় নিশ্চিত করা
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
                # যদি ডাটা এক হয় (কিছুই না বদলায়), তবে এডিট এরর দিবে, তখন আমরা জাস্ট অ্যানসার করবো
                await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


async def generate_mela_report(session, house_id, today_date):
    """আজকের তারিখে মেলা থাকলে সংক্ষিপ্ত রিপোর্ট রিটার্ন করে (থানা + কাউন্ট)।"""
    from datetime import date

    # সব মেলা খুঁজুন (একদিনে একাধিক মেলা হতে পারে)
    mela_res = await session.execute(
        select(Mela)
        .where(Mela.house_id == house_id, Mela.activity_date == today_date)
        .options(selectinload(Mela.assignments))
    )
    melas = mela_res.scalars().all()
    if not melas:
        return ""

    # সব মেলার অ্যাসাইনমেন্ট থেকে কোড সংগ্রহ
    all_codes = set()
    for mela in melas:
        for a in mela.assignments:
            if a.retailer_code:
                all_codes.add(a.retailer_code.upper())

    # অ্যাক্টিভেশন গণনা
    act_res = await session.execute(
        select(LiveActivation.retailer_code, func.count(LiveActivation.id))
        .where(LiveActivation.house_id == house_id, LiveActivation.activation_date == today_date.strftime("%d-%b-%Y"))
        .group_by(LiveActivation.retailer_code)
    )
    activation_map = {str(code).upper(): count for code, count in act_res.all()}

    # প্রতিটি মেলার জন্য থানা + কাউন্ট
    mela_lines = []
    for mela in melas:
        thana = mela.thana or "N/A"

        # মেলার অ্যাসাইনমেন্ট থেকে কোড গণনা
        mela_codes = set()
        for a in mela.assignments:
            if a.retailer_code:
                mela_codes.add(a.retailer_code.upper())

        # শুধু এই মেলার কোডগুলোর অ্যাক্টিভেশন গণনা
        mela_ga_count = sum(activation_map.get(code, 0) for code in mela_codes)

        mela_lines.append(f"📍 {thana}: {bn_num(mela_ga_count)}টি অ্যাক্টিভেশন")

    # সর্বমোট
    total_ga = sum(activation_map.get(code.upper(), 0) for code in all_codes)

    report = f"""
---------------------------
🎪 মেলা রিপোর্ট (আজ):
{chr(10).join(mela_lines)}
মোট: {bn_num(total_ga)}টি অ্যাক্টিভেশন
---------------------------"""
    return report


# ==========================================
# ৫. বিস্তারিত ওয়ার্কফ্লো - ফিল্ড ফোর্স টাইপ সিলেকশন
# ==========================================

@router.callback_query(F.data.startswith("ga_details_menu_"))
async def ga_details_menu(callback: CallbackQuery):
    """বিস্তারিত মেনু - ফিল্ড ফোর্স টাইপ সিলেকশন"""
    house_id = int(callback.data.split("_")[3])

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            await callback.answer("হাউজ পাওয়া যায়নি", show_alert=True)
            return

        # আজকের তারিখ
        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y")

        # সকল ফিল্ড ফোর্স লোড (assisted_retailer_code সহ)
        ff_res = await session.execute(
            select(FieldForce).where(
                FieldForce.house_id == house.id,
                func.lower(FieldForce.status) == 'active'
            )
        )
        field_forces = ff_res.scalars().all()

        # কোড -> ফিল্ড ফোর্স টাইপ ম্যাপিং তৈরি
        rso_codes = set()
        bp_codes = set()
        cc_codes = set()
        code_to_ff_map = {}  # কোড -> field_force object (দ্রুত অ্যাক্সেসের জন্য)

        for ff in field_forces:
            code = str(ff.assisted_retailer_code).replace("'", "").strip().upper() if ff.assisted_retailer_code else ""
            if not code:
                continue

            ff_type = str(ff.type).strip().upper()
            code_to_ff_map[code] = ff

            if ff_type in ['SR', 'RSO']:
                rso_codes.add(code)
            elif ff_type == 'BP':
                bp_codes.add(code)
            elif ff_type == 'CC':
                cc_codes.add(code)

        # আজকের অ্যাক্টিভেশন লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()

        if not activations:
            await callback.message.edit_text(
                f"❌ আজকের জন্য কোনো অ্যাক্টিভেশন পাওয়া যায়নি।",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 ফিরে যান", callback_data=f"ga_hsel_{house.id}").as_markup()
            )
            await callback.answer()
            return

        # গণনা (retailer_code দিয়ে ম্যাচ করে)
        rso_retailers = set()  # ইউনিক রিটেইলার কোড
        bp_retailers = set()
        cc_retailers = set()
        retailer_codes = set()

        for act in activations:
            code = str(act.retailer_code).replace("'", "").strip().upper() if act.retailer_code else ""
            if not code:
                continue

            if code in rso_codes:
                rso_retailers.add(code)
            elif code in bp_codes:
                bp_retailers.add(code)
            elif code in cc_codes:
                cc_retailers.add(code)
            else:
                # কোনো ফিল্ড ফোর্সের সাথে মিলে না = রিটেইলার
                retailer_codes.add(code)

        # কীবোর্ড বিল্ড
        builder = InlineKeyboardBuilder()

        # ফিল্ড ফোর্স টাইপ অপশন (ইউনিক রিটেইলার কোড সংখ্যা)
        if rso_retailers:
            builder.button(text=f"👨‍💼 আরএসও ({bn_num(len(rso_retailers))}জন)", callback_data=f"ga_details_type_{house_id}_RSO")
        if bp_retailers:
            builder.button(text=f"👷‍♂️ বিপি ({bn_num(len(bp_retailers))}জন)", callback_data=f"ga_details_type_{house_id}_BP")
        if cc_retailers:
            builder.button(text=f"🎧 সিসি ({bn_num(len(cc_retailers))}জন)", callback_data=f"ga_details_type_{house_id}_CC")
        if retailer_codes:
            builder.button(text=f"🏪 রিটেইলার ({bn_num(len(retailer_codes))}জন)", callback_data=f"ga_details_type_{house_id}_RETAILER")

        builder.button(text="🔙 ফিরে যান", callback_data=f"ga_hsel_{house.id}")
        builder.adjust(1)

        text = f"📋 **{house.name}** - ফিল্ড ফোর্স টাইপ নির্বাচন করুন\n"
        text += "─────────────────────\n"
        text += "নিচের তালিকা থেকে একটি টাইপ সিলেক্ট করুন:"

        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()


# ==========================================
# ৬. ফিল্ড ফোর্স লিস্ট (পেজিনেশন + সার্চ)
# ==========================================

@router.callback_query(F.data.startswith("ga_details_type_"))
async def ga_details_ff_list(callback: CallbackQuery):
    """নির্দিষ্ট ফিল্ড ফোর্স টাইপের লিস্ট - শুধুমাত্র আজকের অ্যাক্টিভেশন আছে এমন"""
    parts = callback.data.split("_")
    house_id = int(parts[3])
    ff_type = parts[4]  # RSO, BP, CC, RETAILER

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            await callback.answer("হাউজ পাওয়া যায়নি", show_alert=True)
            return

        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y")

        # সকল ফিল্ড ফোর্স লোড
        ff_res = await session.execute(
            select(FieldForce).where(
                FieldForce.house_id == house.id,
                func.lower(FieldForce.status) == 'active'
            )
        )
        field_forces = ff_res.scalars().all()

        # কোড -> ফিল্ড ফোর্স ম্যাপিং
        rso_codes = set()
        bp_codes = set()
        cc_codes = set()
        code_to_ff_map = {}

        for ff in field_forces:
            code = str(ff.assisted_retailer_code).replace("'", "").strip().upper() if ff.assisted_retailer_code else ""
            if not code:
                continue

            ff_type_upper = str(ff.type).strip().upper()
            code_to_ff_map[code] = ff

            if ff_type_upper in ['SR', 'RSO']:
                rso_codes.add(code)
            elif ff_type_upper == 'BP':
                bp_codes.add(code)
            elif ff_type_upper == 'CC':
                cc_codes.add(code)

        # আজকের অ্যাক্টিভেশন লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()

        if not activations:
            await callback.message.edit_text(
                f"❌ আজকের জন্য কোনো অ্যাক্টিভেশন পাওয়া যায়নি।",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 ফিরে যান", callback_data=f"ga_details_menu_{house.id}").as_markup()
            )
            await callback.answer()
            return

        # শুধুমাত্র আজকের অ্যাক্টিভেশন আছে এমন কোড সেট তৈরি
        activation_codes = set()
        for act in activations:
            code = str(act.retailer_code).replace("'", "").strip().upper() if act.retailer_code else ""
            if code:
                activation_codes.add(code)

        # টার্গেট কোড সেট নির্ধারণ
        if ff_type == "RETAILER":
            target_codes = set()
            for act in activations:
                code = str(act.retailer_code).replace("'", "").strip().upper() if act.retailer_code else ""
                if code and code not in rso_codes and code not in bp_codes and code not in cc_codes:
                    target_codes.add(code)
        else:
            # শুধুমাত্র আজকের অ্যাক্টিভেশন আছে এমন ফিল্ড ফোর্স দেখাবে
            if ff_type == 'RSO':
                target_codes = rso_codes & activation_codes
            elif ff_type == 'BP':
                target_codes = bp_codes & activation_codes
            elif ff_type == 'CC':
                target_codes = cc_codes & activation_codes
            else:
                target_codes = set()

        # পেজিনেশন (প্রতি পেজে ৫টি)
        limit = 5
        page = 1
        target_codes_list = sorted(list(target_codes))
        total_ff = len(target_codes_list)
        total_pages = max(1, (total_ff + limit - 1) // limit)

        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_codes = target_codes_list[start_idx:end_idx]

        builder = InlineKeyboardBuilder()

        if ff_type == "RETAILER":
            # রিটেলার কোড থেকে নাম নিন
            retailer_res = await session.execute(
                select(Retailer).where(
                    Retailer.house_id == house.id,
                    Retailer.retailer_code.in_(page_codes)
                )
            )
            retailer_map = {r.retailer_code.upper(): r for r in retailer_res.scalars().all()}

            # সব RSO লোড (ITOP সার্চ করতে)
            rso_res = await session.execute(
                select(FieldForce).options(selectinload(FieldForce.retailers))
                .where(FieldForce.house_id == house.id, FieldForce.type.in_(['SR', 'RSO']))
            )
            rso_map = {}
            for rso in rso_res.scalars().all():
                if rso.retailers:
                    for r in rso.retailers:
                        if r.retailer_code:
                            rso_map[str(r.retailer_code).upper()] = rso

            # রিটেইলার লিস্ট (নাম + RSO এর ITOP শেষ তিন সংখ্যা)
            for code in page_codes:
                retailer = retailer_map.get(code.upper())
                name = retailer.name if retailer else code

                # RSO খুঁজুন
                rso = rso_map.get(code.upper())
                rso_itop_suffix = str(rso.itop_number)[-3:] if rso and rso.itop_number else ""

                display_text = f"🏪 {name} ({rso_itop_suffix})" if rso_itop_suffix else f"🏪 {name}"
                builder.button(
                    text=display_text,
                    callback_data=f"ga_details_retailer_{house.id}_{code}"
                )
        else:
            # RSO, BP, CC লিস্ট
            for code in page_codes:
                ff = code_to_ff_map.get(code)
                if ff:
                    builder.button(
                        text=f"👤 {ff.name}",
                        callback_data=f"ga_details_ff_{house.id}_{ff.id}"
                    )

        # পেজিনেশন বাটন (row() দিয়ে আলাদা রো তৈরি)
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(("◀️ পূর্ববর্তী", f"ga_details_page_{house_id}_{ff_type}_{page-1}"))
            if page < total_pages:
                nav_buttons.append(("পরবর্তী ▶️", f"ga_details_page_{house_id}_{ff_type}_{page+1}"))

            for btn_text, btn_data in nav_buttons:
                builder.button(text=btn_text, callback_data=btn_data)

        builder.button(text="🔙 ফিরে যান", callback_data=f"ga_details_menu_{house.id}")

        # প্রতিটি লিস্ট আইটেম আলাদা লাইনে, পেজিনেশন পাশাপাশি, ব্যাক আলাদা
        if total_pages > 1:
            adjust_list = [1] * len(page_codes) + [2, 1]
        else:
            adjust_list = [1] * len(page_codes) + [1]
        builder.adjust(*adjust_list)

        type_label = {"RSO": "আরএসও", "BP": "বিপি", "CC": "সিসি", "RETAILER": "রিটেইলার"}.get(ff_type, ff_type)
        text = f"📋 **{house.name}** - {type_label} লিস্ট (পেজ {bn_num(page)}/{bn_num(total_pages)})\n"
        text += f"─────────────────────\n"
        text += f"মোট: {bn_num(total_ff)}জন"

        if not target_codes:
            text = f"কোনো {type_label} পাওয়া যায়নি।"

        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

    await callback.answer()


# ==========================================
# ৭. পেজিনেশন হ্যান্ডেলার
# ==========================================

@router.callback_query(F.data.startswith("ga_details_page_"))
async def ga_details_pagination(callback: CallbackQuery):
    """পেজিনেশন হ্যান্ডেলার"""
    parts = callback.data.split("_")
    house_id = int(parts[3])
    ff_type = parts[4]  # RSO, BP, CC, RETAILER
    page = int(parts[5])

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            await callback.answer("হাউজ পাওয়া যায়নি", show_alert=True)
            return

        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y")

        # সকল ফিল্ড ফোর্স লোড
        ff_res = await session.execute(
            select(FieldForce).where(
                FieldForce.house_id == house.id,
                func.lower(FieldForce.status) == 'active'
            )
        )
        field_forces = ff_res.scalars().all()

        # কোড -> ফিল্ড ফোর্স ম্যাপিং
        rso_codes = set()
        bp_codes = set()
        cc_codes = set()
        code_to_ff_map = {}

        for ff in field_forces:
            code = str(ff.assisted_retailer_code).replace("'", "").strip().upper() if ff.assisted_retailer_code else ""
            if not code:
                continue

            ff_type_upper = str(ff.type).strip().upper()
            code_to_ff_map[code] = ff

            if ff_type_upper in ['SR', 'RSO']:
                rso_codes.add(code)
            elif ff_type_upper == 'BP':
                bp_codes.add(code)
            elif ff_type_upper == 'CC':
                cc_codes.add(code)

        # আজকের অ্যাক্টিভেশন লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()

        limit = 5

        # শুধুমাত্র আজকের অ্যাক্টিভেশন আছে এমন কোড সেট তৈরি
        activation_codes = set()
        for act in activations:
            code = str(act.retailer_code).replace("'", "").strip().upper() if act.retailer_code else ""
            if code:
                activation_codes.add(code)

        # টার্গেট কোড সেট নির্ধারণ
        if ff_type == "RETAILER":
            target_codes = set()
            for act in activations:
                code = str(act.retailer_code).replace("'", "").strip().upper() if act.retailer_code else ""
                if code and code not in rso_codes and code not in bp_codes and code not in cc_codes:
                    target_codes.add(code)
        else:
            # শুধুমাত্র আজকের অ্যাক্টিভেশন আছে এমন ফিল্ড ফোর্স দেখাবে
            if ff_type == 'RSO':
                target_codes = rso_codes & activation_codes
            elif ff_type == 'BP':
                target_codes = bp_codes & activation_codes
            elif ff_type == 'CC':
                target_codes = cc_codes & activation_codes
            else:
                target_codes = set()

        target_codes_list = sorted(list(target_codes))
        total_ff = len(target_codes_list)
        total_pages = max(1, (total_ff + limit - 1) // limit)

        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_codes = target_codes_list[start_idx:end_idx]

        builder = InlineKeyboardBuilder()

        if ff_type == "RETAILER":
            # রিটেলার কোড থেকে নাম নিন
            retailer_res = await session.execute(
                select(Retailer).where(
                    Retailer.house_id == house.id,
                    Retailer.retailer_code.in_(page_codes)
                )
            )
            retailer_map = {r.retailer_code.upper(): r for r in retailer_res.scalars().all()}

            # সব RSO লোড (ITOP সার্চ করতে)
            rso_res = await session.execute(
                select(FieldForce).options(selectinload(FieldForce.retailers))
                .where(FieldForce.house_id == house.id, FieldForce.type.in_(['SR', 'RSO']))
            )
            rso_map = {}
            for rso in rso_res.scalars().all():
                if rso.retailers:
                    for r in rso.retailers:
                        if r.retailer_code:
                            rso_map[str(r.retailer_code).upper()] = rso

            for code in page_codes:
                retailer = retailer_map.get(code.upper())
                name = retailer.name if retailer else code

                # RSO খুঁজুন
                rso = rso_map.get(code.upper())
                rso_itop_suffix = str(rso.itop_number)[-3:] if rso and rso.itop_number else ""

                display_text = f"🏪 {name} ({rso_itop_suffix})" if rso_itop_suffix else f"🏪 {name}"
                builder.button(
                    text=display_text,
                    callback_data=f"ga_details_retailer_{house.id}_{code}"
                )
        else:
            for code in page_codes:
                ff = code_to_ff_map.get(code)
                if ff:
                    builder.button(
                        text=f"👤 {ff.name}",
                        callback_data=f"ga_details_ff_{house.id}_{ff.id}"
                    )

        # পেজিনেশন
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(("◀️ পূর্ববর্তী", f"ga_details_page_{house_id}_{ff_type}_{page-1}"))
            if page < total_pages:
                nav_buttons.append(("পরবর্তী ▶️", f"ga_details_page_{house_id}_{ff_type}_{page+1}"))

            for btn_text, btn_data in nav_buttons:
                builder.button(text=btn_text, callback_data=btn_data)

        builder.button(text="🔙 ফিরে যান", callback_data=f"ga_details_menu_{house.id}")

        # প্রতিটি লিস্ট আইটেম আলাদা লাইনে, পেজিনেশন পাশাপাশি, ব্যাক আলাদা
        if total_pages > 1:
            adjust_list = [1] * len(page_codes) + [2, 1]
        else:
            adjust_list = [1] * len(page_codes) + [1]
        builder.adjust(*adjust_list)

        type_label = {"RSO": "আরএসও", "BP": "বিপি", "CC": "সিসি", "RETAILER": "রিটেইলার"}.get(ff_type, ff_type)
        text = f"📋 **{house.name}** - {type_label} লিস্ট (পেজ {bn_num(page)}/{bn_num(total_pages)})\n"
        text += f"─────────────────────\n"
        text += f"মোট: {bn_num(total_ff)}জন"

        if not target_codes:
            text = f"কোনো {type_label} পাওয়া যায়নি।"

        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

    await callback.answer()


# ==========================================
# ৮. ফিল্ড ফোর্স সিলেক্ট - বিস্তারিত ডাটা দেখানো
# ==========================================

@router.callback_query(F.data.startswith("ga_details_ff_"))
async def ga_details_ff_select(callback: CallbackQuery):
    """নির্দিষ্ট ফিল্ড ফোর্সের বিস্তারিত ডাটা"""
    parts = callback.data.split("_")
    house_id = int(parts[3])
    ff_id = int(parts[4])

    async with async_session() as session:
        house = await session.get(House, house_id)
        ff = await session.execute(
            select(FieldForce).options(selectinload(FieldForce.retailers)).where(FieldForce.id == ff_id)
        )
        ff = ff.scalar_one_or_none()

        if not house or not ff:
            await callback.answer("ডাটা পাওয়া যায়নি", show_alert=True)
            return

        # আজকের তারিখ
        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y")

        # ফিল্ড ফোর্সের কোড
        ff_code = str(ff.assisted_retailer_code).replace("'", "").strip().upper() if ff.assisted_retailer_code else ""
        ff_type = str(ff.type).strip().upper()

        # অ্যাক্টিভেশন ডাটা লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()

        # এই ফিল্ড ফোর্সের সমস্ত অ্যাক্টিভেশন ফিল্টার
        target_codes = {ff_code}

        # RSO হলে তার রিটেইলারদের কোডও যোগ
        if ff_type in ['SR', 'RSO'] and ff.retailers:
            for r in ff.retailers:
                r_code = str(r.retailer_code).replace("'", "").strip().upper()
                if r_code:
                    target_codes.add(r_code)

        # ফিল্টার করা অ্যাক্টিভেশন
        filtered_activations = [a for a in activations if str(a.retailer_code).replace("'", "").strip().upper() in target_codes]

        if not filtered_activations:
            await callback.message.edit_text(
                f"❌ আজকের জন্য কোনো অ্যাক্টিভেশন পাওয়া যায়নি।",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 ফিরে যান", callback_data=f"ga_details_type_{house_id}_{ff_type}").as_markup()
            )
            await callback.answer()
            return

        # ডাটা ফরম্যাটিং
        text = format_ff_details(ff, filtered_activations, house)

        # ব্যাক ও রিফ্রেশ বাটন
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ", callback_data=f"ga_details_ff_{house_id}_{ff_id}")
        builder.button(text="🔙 ফিরে যান", callback_data=f"ga_details_type_{house_id}_{ff_type}")
        builder.adjust(2)

        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            pass  # যদি একই মেসেজ হয়, কিছু করতে হবে না

    await callback.answer()


# ==========================================
# ৯. রিটেইলার সিলেক্ট - বিস্তারিত ডাটা দেখানো
# ==========================================

@router.callback_query(F.data.startswith("ga_details_retailer_"))
async def ga_details_retailer_select(callback: CallbackQuery):
    """নির্দিষ্ট রিটেইলারের বিস্তারিত ডাটা"""
    parts = callback.data.split("_")
    house_id = int(parts[3])
    # রিটেইলার কোডে underscores থাকতে পারে, তাই সব অংশ যোগ করা
    retailer_code = "_".join(parts[4:])  # retailer code (may contain underscores)

    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            await callback.answer("হাউজ পাওয়া যায়নি", show_alert=True)
            return

        # রিটেইলার খুঁজুন
        retailer_res = await session.execute(
            select(Retailer).where(Retailer.house_id == house.id, Retailer.retailer_code == retailer_code)
        )
        retailer = retailer_res.scalar_one_or_none()

        # রিটেইলার খুঁজে না পেলে নতুন তৈরি করুন
        if not retailer:
            retailer = Retailer(
                house_id=house.id,
                retailer_code=retailer_code,
                name=retailer_code,  # নাম না থাকলে কোডই দেখাবে
                field_force_id=None  # ডিফল্ট None
            )

        if not retailer:
            await callback.answer("রিটেইলার পাওয়া যায়নি", show_alert=True)
            return

        # আজকের তারিখ
        from datetime import date
        today_str = date.today().strftime("%d-%b-%Y")

        # অ্যাক্টিভেশন ডাটা লোড
        p_filters = (await session.execute(select(GAProductFilter.product_code).where(GAProductFilter.house_id == house.id))).scalars().all()

        act_query = select(LiveActivation).where(
            LiveActivation.house_id == house.id,
            LiveActivation.activation_date == today_str,
            LiveActivation.retailer_code == retailer_code,
            not_(LiveActivation.product_code.in_(p_filters))
        )
        activations = (await session.execute(act_query)).scalars().all()

        if not activations:
            await callback.message.edit_text(
                f"❌ আজকের জন্য কোনো অ্যাক্টিভেশন পাওয়া যায়নি।",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 ফিরে যান", callback_data=f"ga_details_type_{house_id}_RETAILER").as_markup()
            )
            await callback.answer()
            return

        # ডাটা ফরম্যাটিং (রিটেইলারের জন্য) - async ফাংশন
        text = await get_retailer_details_formatted(session, retailer, activations)

        # ব্যাক ও রিফ্রেশ বাটন
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ", callback_data=f"ga_details_retailer_{house_id}_{retailer_code}")
        builder.button(text="🔙 ফিরে যান", callback_data=f"ga_details_type_{house_id}_RETAILER")
        builder.adjust(2)

        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            pass  # যদি একই মেসেজ হয়, কিছু করতে হবে না

    await callback.answer()


# ==========================================
# ১১. সার্চ হ্যান্ডেলার (বেসিক)
# ==========================================

@router.callback_query(F.data.startswith("ga_details_search_"))
async def ga_details_search(callback: CallbackQuery):
    """সার্চ অপশন - ফিল্ড ফোর্স সার্চ"""
    parts = callback.data.split("_")
    house_id = int(parts[3])
    ff_type = parts[4]  # RSO, BP, CC, RETAILER

    type_label = {
        "RSO": "আরএসও",
        "BP": "বিপি",
        "CC": "সিসি",
        "RETAILER": "রিটেইলার"
    }.get(ff_type, ff_type)

    await callback.message.edit_text(
        f"🔍 **{type_label} সার্চ**\n"
        "─────────────────────\n"
        "আপনি নিম্নলিখিত যেকোনো তথ্য দিয়ে সার্চ করতে পারেন:\n"
        "• নাম\n"
        "• অ্যাসিস্ট্যাড কোড\n"
        "• আইটপ নাম্বার\n"
        "• পুল নাম্বার\n\n"
        "⚠️ সার্চ ফিচার শীঘ্রই আসবে।\n"
        "বর্তমানে আপনি তালিকা থেকে সরাসরি নির্বাচন করুন।",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 ফিরে যান",
            callback_data=f"ga_details_type_{house_id}_{ff_type}"
        ).as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


# ==========================================
# ১০. ডাটা ফরম্যাটিং ফাংশন
# ==========================================

def format_ff_details(ff: FieldForce, activations: list, house: House) -> str:
    """ফিল্ড ফোর্সের বিস্তারিত ডাটা ফরম্যাট"""
    from app.Utils.helpers import bn_num

    ff_type = str(ff.type).strip().upper()

    # নাম এবং নাম্বার
    name = ff.name

    # নাম্বার নির্ধারণ (RSO = ITOP, BP/CC = Pool)
    if ff_type in ['SR', 'RSO']:
        number = ff.itop_number or "N/A"
    else:
        number = ff.pool_number or "N/A"

    # কোড এবং রেকর্ড সংখ্যা
    ff_code = str(ff.assisted_retailer_code).replace("'", "").strip() if ff.assisted_retailer_code else "N/A"
    record_count = len(activations)

    # টেক্সট তৈরি
    text = f"<b>{name}</b>\n"
    text += f"{number}\n"
    text += f"{ff_code} • {record_count}\n"
    text += "─────────────────────\n"

    # প্রোডাক্ট কোড অনুযায়ী গ্রুপ
    product_groups = {}
    for act in activations:
        prod_code = str(act.product_code).strip() if act.product_code else "UNKNOWN"
        if prod_code not in product_groups:
            product_groups[prod_code] = []
        product_groups[prod_code].append(act)

    # প্রোডাক্ট কোড অনুযায়ী প্রদর্শন
    first_group = True
    for prod_code, acts in sorted(product_groups.items()):
        if not first_group:
            text += "\n━━━━━━━━━━━━━━\n"
        first_group = False

        # প্রোডাক্ট কোড হেডার
        text += f"<b>{prod_code}</b> • {len(acts)}\n"

        # প্রতিটি অ্যাক্টিভেশন
        for i, act in enumerate(acts):
            text += f"{act.sim_no or 'N/A'}\n"
            text += f"{act.msisdn or 'N/A'}"

            if act.activation_time:
                text += f" • {act.activation_time}"
            text += "\n"

            # তারিখ (শুধু তারিখ দেখাবে, সময় বাদ)
            if act.dh_lifting_date:
                lifting = str(act.dh_lifting_date)[:10] if act.dh_lifting_date else ""
                text += f"Lifting Date: {lifting}\n"
            if act.issue_date:
                issue = str(act.issue_date)[:10] if act.issue_date else ""
                text += f"Issue Date: {issue}"

            if i < len(acts) - 1:
                text += "\n\n"

    return text


async def get_retailer_details_formatted(session, retailer, activations: list) -> str:
    """রিটেইলারের বিস্তারিত ডাটা ফরম্যাট"""
    from app.Utils.helpers import bn_num

    # রিটেইলার RSO খুঁজুন (RSO এর ITOP শেষ ৩ সংখ্যা দেখানোর জন্য)
    rso_itop_suffix = ""
    rso_name = ""
    ff = None

    if retailer:
        # প্রথমে field_force_id চেক করুন
        if retailer.field_force_id:
            ff = await session.get(FieldForce, retailer.field_force_id)

        # যদি না পাওয়া যায়, তাহলে RSO এর retailers লিস্টে খুঁজুন
        if not ff and retailer.retailer_code:
            rso_res = await session.execute(
                select(FieldForce).options(selectinload(FieldForce.retailers))
                .where(FieldForce.house_id == retailer.house_id, FieldForce.type.in_(['SR', 'RSO']))
            )
            for rso in rso_res.scalars().all():
                if rso.retailers:
                    for r in rso.retailers:
                        if r.retailer_code and str(r.retailer_code).strip().upper() == str(retailer.retailer_code).strip().upper():
                            ff = rso
                            break
                if ff:
                    break

    if ff and ff.itop_number:
        rso_itop_suffix = str(ff.itop_number)[-3:]
        rso_name = ff.name

    # নাম এবং নাম্বার
    name = retailer.name if retailer else "Unknown"
    number = str(retailer.itop_number).strip() if retailer and retailer.itop_number else "N/A"

    # রিটেইলারের জন্য RSO এর ITOP শেষ ৩ সংখ্যা দেখাও
    if rso_itop_suffix:
        number = f"{number} ({rso_itop_suffix})"

    # কোড এবং রেকর্ড সংখ্যা
    r_code = str(retailer.retailer_code).replace("'", "").strip() if retailer and retailer.retailer_code else "N/A"
    record_count = len(activations)

    # টেক্সট তৈরি
    text = f"<b>{name}</b>\n"
    text += f"{number}\n"
    text += f"{r_code} • {record_count}\n"
    text += "─────────────────────\n"

    # প্রোডাক্ট কোড অনুযায়ী গ্রুপ
    product_groups = {}
    for act in activations:
        prod_code = str(act.product_code).strip() if act.product_code else "UNKNOWN"
        if prod_code not in product_groups:
            product_groups[prod_code] = []
        product_groups[prod_code].append(act)

    # প্রোডাক্ট কোড অনুযায়ী প্রদর্শন
    first_group = True
    for prod_code, acts in sorted(product_groups.items()):
        if not first_group:
            text += "\n"
        first_group = False

        # প্রোডাক্ট কোড হেডার
        text += f"<b>{prod_code}</b> • {len(acts)}\n"

        # প্রতিটি অ্যাক্টিভেশন
        for i, act in enumerate(acts):
            text += f"{act.sim_no or 'N/A'}\n"
            text += f"{act.msisdn or 'N/A'}"

            if act.activation_time:
                text += f" • {act.activation_time}"
            text += "\n"

            # তারিখ (শুধু তারিখ দেখাবে, সময় বাদ)
            if act.dh_lifting_date:
                lifting = str(act.dh_lifting_date)[:10] if act.dh_lifting_date else ""
                text += f"Lifting Date: {lifting}\n"
            if act.issue_date:
                issue = str(act.issue_date)[:10] if act.issue_date else ""
                text += f"Issue Date: {issue}"

            if i < len(acts) - 1:
                text += "\n\n"

    return text