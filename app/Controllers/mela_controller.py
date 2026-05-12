import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, and_, delete, or_
from sqlalchemy.orm import selectinload

# মডেল ইম্পোর্ট
from app.Models.mela import Mela, MelaType, MelaActivity, MelaEligibleBTS, MelaAssignment, mela_bts_link
from app.Models.bts import BTS
from app.Models.field_force import FieldForce
from app.Models.retailer import Retailer
from app.Models.house import House
from app.Models.user import User
from app.Models.activation import Activation

from app.Services.db_service import async_session
from app.Utils.helpers import bn_num
from config.settings import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# 1. FSM STATES
# ==========================================
class MelaWizard(StatesGroup):
    instr_msg_id = State()
    house_id = State()
    activity_date = State()
    mela_type = State()
    activity = State()
    thana = State()
    bts = State()
    rso = State()
    bp = State()
    retailer = State()
    manual_retailer = State()

class MelaUpdateForm(StatesGroup):
    mela_id = State()
    field = State()
    value = State()

class MelaSearchState(StatesGroup):
    query = State()


def _format_bts_text(bts_items: list) -> str:
    return "".join([
        f" {bn_num(i)} {b.bts_code}-{b.short_address_bn or 'N/A'}\n"
        for i, b in enumerate(bts_items, 1)
    ]) or " N/A\n"


async def _build_retailer_rso_suffix_map(session, ret_objs: list) -> dict:
    rso_id_set = {r.field_force_id for r in ret_objs if r.field_force_id}
    if not rso_id_set:
        return {}
    rso_items = (await session.execute(
        select(FieldForce.id, FieldForce.itop_number).where(FieldForce.id.in_(rso_id_set))
    )).all()
    return {rid: itop for rid, itop in rso_items}


def _format_member_texts(rso_objs: list, bp_objs: list, ret_objs: list, retailer_rso_suffix_map: dict, activation_map: dict = None) -> tuple[str, str, str]:
    if activation_map is None:
        activation_map = {}

    rso_text = "".join([
        f" {bn_num(i)} {r.assisted_retailer_code} ({str(r.itop_number)[-3:] if r.itop_number else '000'}) - {bn_num(activation_map.get(r.assisted_retailer_code.upper() if r.assisted_retailer_code else '', 0))}টি\n"
        for i, r in enumerate(rso_objs, 1)
    ]) or " N/A\n"

    bp_text = "".join([
        f" {bn_num(i)} {b.name or 'N/A'}-{b.assisted_retailer_code or 'N/A'} - {bn_num(activation_map.get(b.assisted_retailer_code.upper() if b.assisted_retailer_code else '', 0))}টি\n"
        for i, b in enumerate(bp_objs, 1)
    ]) or " N/A\n"

    ret_text = "".join([
        f" {bn_num(i)} {r.name or 'N/A'} ({str(retailer_rso_suffix_map.get(r.field_force_id))[-3:] if retailer_rso_suffix_map.get(r.field_force_id) else '000'}) - {bn_num(activation_map.get(r.retailer_code.upper() if r.retailer_code else '', 0))}টি\n"
        for i, r in enumerate(ret_objs, 1)
    ]) or " N/A\n"
    return rso_text, bp_text, ret_text


def _build_mela_report(
    *,
    status_text: str,
    house_name: str,
    display_date: str,
    mela_type_name: str,
    mela_activity_name: str,
    thana_name: str,
    bts_text: str,
    rso_text: str,
    bp_text: str,
    ret_text: str,
    rso_count: int,
    bp_count: int,
    ret_count: int,
    rso_total: int = 0,
    bp_total: int = 0,
    ret_total: int = 0,
    grand_total: int = 0
) -> str:
    header = ""
    if status_text:
        header = f"🎊 <b>অভিনন্দন!</b>\n✅ <b>{status_text}</b>\n━━━━━━━━━━━━━━━━━━━━\n"

    # RSO টোটাল
    rso_section = f"🔹 আরএসও ({bn_num(rso_count)} জন): \n{rso_text}"
    if rso_count > 1 and rso_total > 0:
        rso_section += f"👉 মোট: {bn_num(rso_total)}টি\n"

    # BP টোটাল
    bp_section = f"🔹 বিপি ({bn_num(bp_count)} জন):\n{bp_text}"
    if bp_count > 1 and bp_total > 0:
        bp_section += f"👉 মোট: {bn_num(bp_total)}টি\n"

    # Retailer টোটাল
    ret_section = f"🔹 রিটেইলার ({bn_num(ret_count)} জন): \n{ret_text}"
    if ret_count > 1 and ret_total > 0:
        ret_section += f"👉 মোট: {bn_num(ret_total)}টি\n"

    return (
        f"{header}"
        f"🏢 হাউজ: <b>{house_name}</b>\n"
        f"📅 তারিখ: <b>{display_date}</b>\n"
        f"🏗 ধরণ: <b>{mela_type_name}</b>\n"
        f"🎯 কাজ: <b>{mela_activity_name}</b>\n"
        f"🏘 থানা: <b>{thana_name}</b>\n\n"
        f"📡 <b>বিটিএস কোডসমূহ:</b>\n{bts_text}\n"
        f"👥 <b>অংশগ্রহণকারী মেম্বার:</b>\n"
        f"{rso_section}\n"
        f"{bp_section}\n"
        f"{ret_section}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>মেলার সর্বমোট অ্যাক্টিভেশন: {bn_num(grand_total)}টি</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ==========================================
# ২. কোর ভিউ (একক মেলার বিস্তারিত তথ্য) ✅
# ==========================================
async def render_single_mela_view(message: Message, m_id: int, permissions: list, edit_mode: bool = False, status_text: str = "মেলাটি সফলভাবে সেভ হয়েছে।"):
    async with async_session() as session:
        res = await session.execute(
            select(Mela).options(
                selectinload(Mela.mela_type), selectinload(Mela.mela_activity),
                selectinload(Mela.covered_bts), selectinload(Mela.assignments),
                selectinload(Mela.house)
            ).where(Mela.id == m_id)
        )
        m = res.scalar_one_or_none()
        if not m: return await message.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।")

        bts_text = _format_bts_text(m.covered_bts)

        rso_codes = [a.retailer_code for a in m.assignments if a.role_type == 'RSO']
        bp_codes = [a.retailer_code for a in m.assignments if a.role_type == 'BP']
        ret_codes = [a.retailer_code for a in m.assignments if a.role_type == 'SSO']

        rso_objs = (await session.execute(select(FieldForce).where(FieldForce.assisted_retailer_code.in_(rso_codes)))).scalars().all() if rso_codes else []
        bp_objs = (await session.execute(select(FieldForce).where(FieldForce.assisted_retailer_code.in_(bp_codes)))).scalars().all() if bp_codes else []
        ret_objs = (await session.execute(select(Retailer).where(Retailer.retailer_code.in_(ret_codes)))).scalars().all() if ret_codes else []
        retailer_rso_suffix_map = await _build_retailer_rso_suffix_map(session, ret_objs)

        # অ্যাক্টিভেশন কাউন্ট নিয়ে আসুন (activations টেবিল থেকে)
        mela_date = m.activity_date
        all_codes = rso_codes + bp_codes + ret_codes
        activation_map = {}
        if mela_date and all_codes:
            lower_codes = [c.lower() for c in all_codes]
            act_res = await session.execute(
                select(Activation.retailer_code, func.count(Activation.id))
                .where(
                    Activation.house_id == m.house_id,
                    Activation.activation_date == mela_date,
                    func.lower(Activation.retailer_code).in_(lower_codes)
                )
                .group_by(Activation.retailer_code)
            )
            for code, count in act_res.all():
                activation_map[code.upper() if code else ""] = count

        rso_text, bp_text, ret_text = _format_member_texts(rso_objs, bp_objs, ret_objs, retailer_rso_suffix_map, activation_map)

        # টোটাল কাউন্ট গণনা
        rso_total = sum(activation_map.get(code.upper(), 0) for code in rso_codes)
        bp_total = sum(activation_map.get(code.upper(), 0) for code in bp_codes)
        ret_total = sum(activation_map.get(code.upper(), 0) for code in ret_codes)
        grand_total = rso_total + bp_total + ret_total

        report_text = _build_mela_report(
            status_text=status_text,
            house_name=m.house.name if m.house else "N/A",
            display_date=m.activity_date.strftime('%d-%m-%Y') if m.activity_date else "N/A",
            mela_type_name=m.mela_type.name if m.mela_type else "N/A",
            mela_activity_name=m.mela_activity.name if m.mela_activity else "N/A",
            thana_name=m.thana or "N/A",
            bts_text=bts_text,
            rso_text=rso_text,
            bp_text=bp_text,
            ret_text=ret_text,
            rso_count=len(rso_objs),
            bp_count=len(bp_objs),
            ret_count=len(ret_objs),
            rso_total=rso_total,
            bp_total=bp_total,
            ret_total=ret_total,
            grand_total=grand_total
        )

        builder = InlineKeyboardBuilder()
        if "edit_mela" in permissions: builder.button(text="✏️ এডিট", callback_data=f"melaedit:{m.id}")
        if "delete_mela" in permissions: builder.button(text="🗑 ডিলিট", callback_data=f"mdel_conf_{m.id}")
        builder.button(text="📋 মেলার তালিকা", callback_data=f"mela_list_{m.house_id}_0")
        builder.adjust(2)
        
        if edit_mode: await message.edit_text(report_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else: await message.answer(report_text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ==========================================
# ৩. ড্যাশবোর্ড এবং মেইন এন্ট্রি
# ==========================================
async def render_mela_dashboard(message: Message, house_id: int, permissions: list, edit_mode: bool = False):
    async with async_session() as session:
        house = await session.get(House, house_id)
        count = await session.scalar(select(func.count(Mela.id)).where(Mela.house_id == house_id))
    builder = InlineKeyboardBuilder()
    if "create_mela" in permissions: builder.button(text="➕ নতুন মেলা", callback_data=f"mela_create_{house_id}")
    if count > 0: builder.button(text="📋 মেলার তালিকা", callback_data=f"mela_list_{house_id}_0")
    if count > 0: builder.button(text="🔍 মেলা অনুসন্ধান", callback_data=f"mela_search_{house_id}")
    builder.button(text="🔄 হাউস পরিবর্তন", callback_data="mela_change_house")
    builder.adjust(2)
    text = f"🎪 <b>মেলা ড্যাশবোর্ড</b>\n🏢 হাউজ: <b>{house.name}</b>\n📊 মোট রেকর্ড: <code>{bn_num(count)}</code> টি"
    if edit_mode:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.message(F.text == "🎪 মেলা ম্যানেজমেন্ট")
async def mela_mgmt_start(message: Message, state: FSMContext, permissions: list):
    await state.clear()
    async with async_session() as session:
        is_admin = (int(message.from_user.id) == int(SUPER_ADMIN_ID))
        logger.info(f"mela_mgmt_start: user_id={message.from_user.id}, SUPER_ADMIN_ID={SUPER_ADMIN_ID}, is_admin={is_admin}")
        if is_admin:
            houses = (await session.execute(select(House).where(House.is_active == True, House.subscription_date >= datetime.now()))).scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == message.from_user.id)
            )).scalar_one_or_none()
            houses = [h for h in (user.houses if user else []) if h.is_active and h.subscription_date and h.subscription_date >= datetime.now()]
        logger.info(f"houses count: {len(houses)}")
        if not houses: return await message.answer("❌ হাউজ পাওয়া যায়নি।")
        if len(houses) == 1: return await render_mela_dashboard(message, houses[0].id, permissions, edit_mode=False)
        builder = InlineKeyboardBuilder()
        for h in houses: builder.button(text=f"🏢 {h.name}", callback_data=f"mela_hsel_{h.id}")
        await message.answer("🎪 <b>মেলা ম্যানেজমেন্ট</b>\nহাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mela_hsel_"))
async def handle_hsel(callback: CallbackQuery, state: FSMContext, permissions: list):
    h_id = int(callback.data.split("_")[2])
    await state.clear()
    await render_mela_dashboard(callback.message, h_id, permissions, edit_mode=True)
    await callback.answer()

@router.callback_query(F.data == "mela_change_house")
async def change_house_mela(callback: CallbackQuery, state: FSMContext, permissions: list):
    await state.clear()
    user_id = callback.from_user.id

    async with async_session() as session:
        # সুপার এডমিন চেক
        if int(user_id) == int(SUPER_ADMIN_ID):
            houses = (await session.execute(select(House).where(House.is_active == True, House.subscription_date >= datetime.now()))).scalars().all()
        else:
            user = (await session.execute(
                select(User).options(selectinload(User.houses)).where(User.telegram_id == user_id)
            )).scalar_one_or_none()
            houses = [h for h in (user.houses if user else []) if h.is_active and h.subscription_date and h.subscription_date >= datetime.now()]

        if not houses:
            return await callback.answer("❌ হাউজ পাওয়া যায়নি।", show_alert=True)

        if len(houses) == 1:
            # সরাসরি ড্যাশবোর্ড দেখান
            await render_mela_dashboard(callback.message, houses[0].id, permissions, edit_mode=True)
            await callback.answer()
            return

        builder = InlineKeyboardBuilder()
        for h in houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"mela_hsel_{h.id}")
        
        await callback.message.edit_text("🎪 <b>মেলা ম্যানেজমেন্ট</b>\nহাউজ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# ৪. নতুন মেলা উইজার্ড (Wizard Steps)
# ==========================================
@router.callback_query(F.data.startswith("mela_create_"))
async def mela_create_init(callback: CallbackQuery, state: FSMContext):
    h_id = int(callback.data.split("_")[2])
    await state.update_data(house_id=h_id, bts_ids=[], rso_ids=[], bp_ids=[], ret_ids=[], is_edit_mode=False)
    # ড্যাশবোর্ড মেসেজ ডিলিট করুন
    try:
        await callback.message.delete()
    except Exception:
        # যদি ডিলিট না হয় (পুরানো মেসেজ) তবুও কাজ চালিয়ে যান
        pass
    await callback.message.answer("📅 মেলার তারিখ লিখুন (DD-MM-YYYY):")
    await state.set_state(MelaWizard.activity_date)

@router.message(MelaWizard.activity_date)
async def wizard_date(message: Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text, "%d-%m-%Y").date()
        data = await state.get_data()

        # Edit mode: শুধু তারিখ আপডেট করে প্রোফাইলে ফেরত
        if data.get("is_edit_mode") and data.get("edit_mela_id"):
            async with async_session() as session:
                m = await session.get(Mela, data["edit_mela_id"])
                if not m:
                    await state.clear()
                    return await message.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।")
                m.activity_date = dt
                await session.commit()
            await state.clear()
            return await render_single_mela_view(message, data["edit_mela_id"], data.get("permissions", []), edit_mode=False, status_text="মেলাটি সফলভাবে আপডেট হয়েছে।")

        # Create mode: পরবর্তী ধাপে ধরণ নির্বাচন
        await state.update_data(date_obj=dt, date_str=message.text)
        async with async_session() as session:
            types = (await session.execute(select(MelaType))).scalars().all()
            builder = InlineKeyboardBuilder()
            for t in types: builder.button(text=t.name, callback_data=f"msel_t:{t.id}")
            await message.answer("🏗 মেলার ধরণ নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())
            await state.set_state(MelaWizard.mela_type)
    except: await message.answer("❌ ভুল ফরম্যাট! DD-MM-YYYY দিন।")

@router.callback_query(MelaWizard.mela_type, F.data.startswith("msel_t:"))
async def wizard_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(t_id=int(callback.data.split(":")[1]))
    async with async_session() as session:
        acts = (await session.execute(select(MelaActivity))).scalars().all()
        builder = InlineKeyboardBuilder()
        for a in acts: builder.button(text=a.name, callback_data=f"msel_a:{a.id}")
        await callback.message.edit_text("🎯 এক্টিভিটি নির্বাচন করুন:", reply_markup=builder.adjust(1).as_markup())
        await state.set_state(MelaWizard.activity)

@router.callback_query(MelaWizard.activity, F.data.startswith("msel_a:"))
async def wizard_act(callback: CallbackQuery, state: FSMContext):
    await state.update_data(a_id=int(callback.data.split(":")[1]))
    data = await state.get_data()
    async with async_session() as session:
        thanas = (await session.execute(select(BTS.thana_bn).join(MelaEligibleBTS).where(MelaEligibleBTS.house_id == data['house_id']).distinct().order_by(BTS.thana_bn))).scalars().all()
        builder = InlineKeyboardBuilder()
        for t in thanas: builder.button(text=f"📍 {t}", callback_data=f"msel_th:{t}")
        await callback.message.edit_text("🏘 থানা নির্বাচন করুন (ইনলাইন):", reply_markup=builder.adjust(2).as_markup())
        await state.set_state(MelaWizard.thana)

@router.callback_query(MelaWizard.thana, F.data.startswith("msel_th:"))
async def wizard_bts(callback: CallbackQuery, state: FSMContext):
    th_name = callback.data.split(":")[1]
    await state.update_data(th_name=th_name, bts_offset=0)
    await show_bts_multi(callback, state)

# --- BTS Multi-select ---
async def show_bts_multi(event, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        offset = data.get('bts_offset', 0)
        limit = 5

        # মোট বিটিএস কাউন্ট
        total = await session.scalar(
            select(func.count(BTS.id))
            .join(MelaEligibleBTS)
            .where(BTS.thana_bn == data['th_name'], MelaEligibleBTS.house_id == data['house_id'])
        )

        # পেজ ভিত্তিক বিটিএস লিস্ট
        res = await session.execute(
            select(BTS)
            .join(MelaEligibleBTS)
            .where(BTS.thana_bn == data['th_name'], MelaEligibleBTS.house_id == data['house_id'])
            .order_by(BTS.bts_code)
            .limit(limit)
            .offset(offset)
        )
        bts_list = res.scalars().all()

        builder = InlineKeyboardBuilder()
        selected_ids = data.get('bts_ids', [])
        for b in bts_list:
            status = "✅" if b.id in selected_ids else "🔘"
            addr = b.short_address_bn if getattr(b, "short_address_bn", None) else "N/A"
            builder.button(text=f"{status} {b.bts_code} ({addr})", callback_data=f"mtog_bts:{b.id}")

        builder.adjust(1)

        # পেজিনেশন বাটন
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"bnav_bts:{offset-5}"))
        if offset + limit < total:
            nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"bnav_bts:{offset+5}"))
        if nav:
            builder.row(*nav)

        # পরবর্তী ধাপ বাটন
        is_edit_mode = data.get('is_edit_mode', False)
        edit_mela_id = data.get('edit_mela_id')
        if is_edit_mode and edit_mela_id:
            # এডিট মোডে: সেভ বাটন এবং প্রোফাইলে ফিরুন বাটন
            builder.row(
                InlineKeyboardButton(text="💾 সেভ করুন", callback_data="msave_bts_only"),
                InlineKeyboardButton(text="🔙 প্রোফাইলে ফিরুন", callback_data=f"mview_{edit_mela_id}")
            )
        else:
            # ক্রিয়েট মোডে: মেম্বার সিলেকশনে যান
            builder.row(InlineKeyboardButton(text="➡️ মেম্বার সিলেকশনে যান", callback_data="mfinish_bts"))

        text = (
            f"📡 <b>{data['th_name']}</b> বিটিএস সিলেক্ট করুন:\n"
            f"মোট: {bn_num(total)}টি (প্রতি পেজে ৫টি করে দেখানো হচ্ছে)"
        )
        if is_edit_mode and edit_mela_id:
            text += "\n\nℹ️ এডিট মোড: বিটিএস সিলেকশন শেষে 'সেভ করুন' বাটনে ক্লিক করুন।"
        if isinstance(event, Message):
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(MelaWizard.bts)

@router.callback_query(MelaWizard.bts, F.data.startswith("bnav_bts:"))
async def nav_bts_pages(callback: CallbackQuery, state: FSMContext):
    new_offset = int(callback.data.split(":")[1])
    if new_offset < 0:
        new_offset = 0
    await state.update_data(bts_offset=new_offset)
    await show_bts_multi(callback, state)
    await callback.answer()

@router.callback_query(MelaWizard.bts, F.data.startswith("mtog_bts:"))
async def toggle_bts(callback: CallbackQuery, state: FSMContext):
    b_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    ids = list(data.get('bts_ids', []))
    if b_id in ids: ids.remove(b_id)
    else: ids.append(b_id)
    await state.update_data(bts_ids=ids)
    await show_bts_multi(callback, state)
    await callback.answer()

# ==========================================
# ৫. মেম্বার সিলেকশন (RSO, BP, Retailer) ✅
# ==========================================
@router.callback_query(MelaWizard.bts, F.data == "mfinish_bts")
async def finish_bts_start_rso(callback: CallbackQuery, state: FSMContext):
    await show_rso_multi(callback, state)

async def show_rso_multi(event, state: FSMContext):
    data = await state.get_data()
    is_edit_mode = data.get('is_edit_mode', False)
    async with async_session() as session:
        res = await session.execute(select(FieldForce).where(FieldForce.house_id == data['house_id'], FieldForce.type.in_(['SR', 'RSO']), func.lower(FieldForce.status) == 'active'))
        items = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for r in items:
            status = "✅" if r.id in data.get('rso_ids', []) else "🔘"
            builder.button(text=f"{status} {r.assisted_retailer_code} ({str(r.itop_number)[-3:]})", callback_data=f"mtog_rso:{r.id}")
        
        if is_edit_mode:
            # এডিট মোডে: সেভ করুন এবং প্রোফাইলে ফিরুন বাটন
            builder.row(
                InlineKeyboardButton(text="💾 সেভ করুন", callback_data="msave_rso_only"),
                InlineKeyboardButton(text="🔙 প্রোফাইলে ফিরুন", callback_data=f"mview_{data.get('edit_mela_id')}")
            )
        else:
            # ক্রিয়েট মোডে: বিপি সিলেকশনে যান
            builder.button(text="➡️ বিপি সিলেকশনে যান", callback_data="mfinish_rso")
        
        await event.message.edit_text("👤 <b>আরএসও নির্বাচন করুন:</b>", reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")
    await state.set_state(MelaWizard.rso)

@router.callback_query(MelaWizard.rso, F.data.startswith("mtog_rso:"))
async def toggle_rso(callback: CallbackQuery, state: FSMContext):
    r_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    ids = list(data.get('rso_ids', []))
    if r_id in ids: ids.remove(r_id)
    else: ids.append(r_id)
    # আরএসও পরিবর্তন হলে রিটেলার আইডি রিসেট করুন
    await state.update_data(rso_ids=ids, ret_ids=[])
    await show_rso_multi(callback, state)
    await callback.answer()

@router.callback_query(MelaWizard.rso, F.data == "mfinish_rso")
async def finish_rso_start_ret(callback: CallbackQuery, state: FSMContext):
    await show_bp_multi(callback, state)

async def show_bp_multi(event, state: FSMContext):
    data = await state.get_data()
    is_edit_mode = data.get('is_edit_mode', False)
    async with async_session() as session:
        res = await session.execute(select(FieldForce).where(FieldForce.house_id == data['house_id'], FieldForce.type == 'BP', func.lower(FieldForce.status) == 'active'))
        items = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for b in items:
            status = "✅" if b.id in data.get('bp_ids', []) else "🔘"
            bp_name = (b.name or "N/A").strip() if b.name else "N/A"
            bp_code = (b.assisted_retailer_code or "N/A").strip() if b.assisted_retailer_code else "N/A"
            builder.button(text=f"{status} {bp_name} ({bp_code})", callback_data=f"mtog_bp:{b.id}")
        
        if is_edit_mode:
            # এডিট মোডে: সেভ করুন এবং লিস্টে ফিরুন বাটন
            builder.row(
                InlineKeyboardButton(text="💾 সেভ করুন", callback_data="msave_bp_only"),
                InlineKeyboardButton(text="🔙 লিস্টে ফিরুন", callback_data=f"mview_{data.get('edit_mela_id')}")
            )
        else:
            # ক্রিয়েট মোডে: রিটেইলার সিলেকশনে যান
            builder.button(text="➡️ রিটেইলার সিলেকশনে যান", callback_data="mfinish_bp")
        
        await event.message.edit_text("👷‍♂️ <b>বিপি নির্বাচন করুন:</b>", reply_markup=builder.adjust(1).as_markup(), parse_mode="HTML")
    await state.set_state(MelaWizard.bp)

@router.callback_query(MelaWizard.bp, F.data.startswith("mtog_bp:"))
async def toggle_bp(callback: CallbackQuery, state: FSMContext):
    b_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    ids = list(data.get('bp_ids', []))
    if b_id in ids: ids.remove(b_id)
    else: ids.append(b_id)
    await state.update_data(bp_ids=ids)
    await show_bp_multi(callback, state)
    await callback.answer()

@router.callback_query(MelaWizard.bp, F.data == "mfinish_bp")
async def finish_bp_start_ret(callback: CallbackQuery, state: FSMContext):
    await state.update_data(ret_offset=0)
    await show_ret_multi(callback, state)

# --- Retailer Multi-select with Pagination & Save Button ✅ ---
async def show_ret_multi(event, state: FSMContext):
    data = await state.get_data()
    offset, limit = data.get('ret_offset', 0), 5
    is_edit_mode = data.get('is_edit_mode', False)
    house_id = data.get('house_id')
    async with async_session() as session:
        selected_ids = data.get('ret_ids', [])
        rso_ids = data.get('rso_ids', [])
        
        # এখন UI-তে দেখানোর জন্য রিটেইলার লিস্ট তৈরি করুন
        # বেস ফিল্টার: শুধুমাত্র sim_seller == 'Y' এবং নির্বাচিত RSO এর অধীনে (যদি RSO নির্বাচিত থাকে)
        base_filter = and_(
            Retailer.field_force_id.in_(rso_ids) if rso_ids else True,
            Retailer.sim_seller == 'Y',
            Retailer.house_id == house_id
        )
        
        # যদি এডিট মোড হয়, তাহলে আগে থেকে নির্বাচিত রিটেইলারগুলোও দেখানো উচিত (তারা যদি শর্ত পূরণ না করে)
        if is_edit_mode and selected_ids:
            base_filter = or_(base_filter, Retailer.id.in_(selected_ids))
        
        q_base = (select(Retailer, FieldForce.itop_number)
            .join(FieldForce, Retailer.field_force_id == FieldForce.id)
            .where(base_filter))
        
        total = await session.scalar(select(func.count()).select_from(q_base.subquery()))
        res = (await session.execute(q_base.order_by(Retailer.name).limit(limit).offset(offset))).all()
        
        builder = InlineKeyboardBuilder()
        for r, itop in res:
            status = "✅" if r.id in selected_ids else "🔘"
            builder.button(text=f"{status} {r.name[:15]} ({str(itop)[-3:]})", callback_data=f"mtog_ret:{r.id}")
        
        builder.adjust(1)
        nav = []
        if offset > 0: nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"mnav_ret:{offset-5}"))
        if offset + limit < total: nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"mnav_ret:{offset+5}"))
        if nav: builder.row(*nav)
        
        # ম্যানুয়ালি রিটেইলার যোগ করার বাটন
        builder.row(InlineKeyboardButton(text="➕ ম্যানুয়ালি রিটেইলার যোগ করুন", callback_data="mret_manual_add"))
        
        builder.row(InlineKeyboardButton(text="💾 মেলা সেভ করুন", callback_data="msave_final"))
        
        text = f"🏬 <b>রিটেইলার নির্বাচন করুন:</b> ({bn_num(total)} জন)\n"
        text += "শুধুমাত্র সিম সেলার (sim_seller = 'Y') রিটেইলার দেখানো হচ্ছে।\n"
        text += "সিলেকশন শেষ হলে সেভ বাটনে ক্লিক করুন।"
        if isinstance(event, Message):
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(MelaWizard.retailer)

@router.callback_query(MelaWizard.retailer, F.data.startswith(("mtog_ret:", "mnav_ret:")))
async def handle_ret_action(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if parts[0] == "mnav_ret": await state.update_data(ret_offset=int(parts[1]))
    else:
        r_id = int(parts[1])
        data = await state.get_data()
        ids = list(data.get('ret_ids', []))
        if r_id in ids: ids.remove(r_id)
        else: ids.append(r_id)
        await state.update_data(ret_ids=ids)
    await show_ret_multi(callback, state)
    await callback.answer()

@router.callback_query(MelaWizard.retailer, F.data == "mret_manual_add")
async def manual_retailer_add(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 <b>রিটেইলার কোড লিখুন:</b>\n"
        "একটি বা একাধিক কোড দিতে পারেন।\n"
        "• কমা দিয়ে: <code>R123456, R234567, R345678</code>\n"
        "• প্রতি লাইনে: <code>R123456\nR234567\nR345678</code>\n"
        "রিটেইলার ডাটাবেসে থাকতে হবে।",
        parse_mode="HTML"
    )
    await state.set_state(MelaWizard.manual_retailer)
    await callback.answer()

@router.message(MelaWizard.manual_retailer)
async def handle_manual_retailer_code(message: Message, state: FSMContext):
    input_text = message.text.strip()
    if not input_text:
        await message.answer("❌ রিটেইলার কোড খালি থাকতে পারে না। আবার চেষ্টা করুন:")
        return

    # কমা বা নিউলাইন দিয়ে কোড আলাদা করুন (বড় অক্ষরে রূপান্তর)
    codes = [c.strip().upper() for c in input_text.replace('\n', ',').split(',') if c.strip()]
    if not codes:
        await message.answer("❌ কোনো রিটেইলার কোড পাওয়া যায়নি। আবার চেষ্টা করুন:")
        return

    async with async_session() as session:
        # সব কোড খুঁজে বের করুন (case-insensitive)
        lower_codes = [c.lower() for c in codes]
        retailers = await session.execute(
            select(Retailer).where(func.lower(Retailer.retailer_code).in_(lower_codes))
        )
        found_map = {r.retailer_code.upper() if r.retailer_code else "": r for r in retailers.scalars().all()}

        # বর্তমান নির্বাচিত রিটেইলার আইডি গুলো নিন
        data = await state.get_data()
        selected_ids = list(data.get('ret_ids', []))

        added = []
        not_found = []
        already_selected = []

        for code in codes:
            retailer = found_map.get(code)
            if not retailer:
                not_found.append(code)
            elif retailer.id in selected_ids:
                already_selected.append(code)
            else:
                selected_ids.append(retailer.id)
                added.append(code)

        await state.update_data(ret_ids=selected_ids)

        # রেসপন্স মেসেজ তৈরি
        response_parts = []
        if added:
            response_parts.append(f"✅ যোগ করা হয়েছে ({len(added)}টি): " + ", ".join(added))
        if already_selected:
            response_parts.append(f"ℹ️ ইতিমধ্যে আছে ({len(already_selected)}টি): " + ", ".join(already_selected))
        if not_found:
            response_parts.append(f"❌ পাওয়া যায়নি ({len(not_found)}টি): " + ", ".join(not_found))

        await message.answer("\n".join(response_parts), parse_mode="HTML")

        # রিটেইলার সিলেকশন পেজে ফিরে যান
        await show_ret_multi(message, state)

# ==========================================
# ৬. সেভ, এডিট এবং ডিলিট লজিক ✅
# ==========================================
@router.callback_query(F.data == "msave_final")
async def save_mela_wizard(callback: CallbackQuery, state: FSMContext, permissions: list):
    data = await state.get_data()
    is_edit = data.get('is_edit_mode', False)
    async with async_session() as session:
        try:
            bts = (await session.execute(select(BTS).where(BTS.id.in_(data.get('bts_ids', []))))).scalars().all()
            if is_edit:
                m = await session.get(Mela, data['edit_mela_id'], options=[selectinload(Mela.covered_bts)])
                await session.execute(delete(MelaAssignment).where(MelaAssignment.mela_id == m.id))
            else:
                m = Mela(house_id=data['house_id'], activity_date=data['date_obj'], mela_type_id=data['t_id'], mela_activity_id=data['a_id'], thana=data['th_name'], location=", ".join([b.short_address_bn or 'N/A' for b in bts]))
                session.add(m)
            
            m.covered_bts = bts
            m.location = ", ".join([b.short_address_bn or 'N/A' for b in bts])  # লোকেশন আপডেট (শর্ট এড্রেস)

            # নতুন রেকর্ড হলে আগে ID নিশ্চিত করা
            await session.flush()

            rso_objs = (await session.execute(select(FieldForce).where(FieldForce.id.in_(data.get('rso_ids', []))))).scalars().all()
            bp_objs = (await session.execute(select(FieldForce).where(FieldForce.id.in_(data.get('bp_ids', []))))).scalars().all()
            ret_objs = (await session.execute(select(Retailer).where(Retailer.id.in_(data.get('ret_ids', []))))).scalars().all()

            # মেম্বার অ্যাসাইনমেন্ট (relationship lazy-load এড়াতে direct mela_id ব্যবহার)
            assignments = []
            for ff in rso_objs:
                assignments.append(MelaAssignment(mela_id=m.id, retailer_code=ff.assisted_retailer_code, role_type='RSO'))
            for ff in bp_objs:
                assignments.append(MelaAssignment(mela_id=m.id, retailer_code=ff.assisted_retailer_code, role_type='BP'))
            for rt in ret_objs:
                assignments.append(MelaAssignment(mela_id=m.id, retailer_code=rt.retailer_code, role_type='SSO'))
            if assignments:
                session.add_all(assignments)

            # রিপোর্ট তৈরির জন্য অতিরিক্ত ডেটা
            house = await session.get(House, m.house_id)
            mela_type = await session.get(MelaType, m.mela_type_id)
            mela_activity = await session.get(MelaActivity, m.mela_activity_id)

            display_date = m.activity_date.strftime("%d-%m-%Y") if m.activity_date else "N/A"
            t_name = mela_type.name if mela_type else "N/A"
            a_name = mela_activity.name if mela_activity else "N/A"

            bts_text = _format_bts_text(bts)
            retailer_rso_suffix_map = await _build_retailer_rso_suffix_map(session, ret_objs)
            rso_text, bp_text, ret_text = _format_member_texts(rso_objs, bp_objs, ret_objs, retailer_rso_suffix_map)

            await session.commit()
            
            # সফল মেসেজ শুধু একটি নোটিফিকেশন হিসেবে
            await callback.answer(f"✅ মেলাটি সফলভাবে {'আপডেট' if is_edit else 'সেভ'} হয়েছে।")
            
            # স্টেট ক্লিয়ার
            await state.clear()
            
            if is_edit:
                # এডিট মোডে: সিঙ্গেল মেলা ভিউতে ফিরুন
                await render_single_mela_view(callback.message, data['edit_mela_id'], permissions, edit_mode=False, status_text="মেলাটি সফলভাবে আপডেট হয়েছে।")
            else:
                # ক্রিয়েট মোডে: সিঙ্গেল মেলা ভিউ দেখানো
                await render_single_mela_view(callback.message, m.id, permissions, edit_mode=True, status_text="মেলাটি সফলভাবে সেভ হয়েছে।")
        except Exception as e:
            logger.error(f"Save mela error: {e}")
            await callback.answer(f"❌ ত্রুটি: {str(e)[:50]}", show_alert=True)

@router.callback_query(F.data == "msave_bts_only")
async def save_bts_only(callback: CallbackQuery, state: FSMContext, permissions: list):
    """এডিট মোডে শুধুমাত্র বিটিএস আপডেট করে সেভ করে"""
    data = await state.get_data()
    if not data.get('is_edit_mode') or not data.get('edit_mela_id'):
        return await callback.answer("❌ এডিট মোডে নেই অথবা মেলা আইডি পাওয়া যায়নি।", show_alert=True)
    
    async with async_session() as session:
        try:
            # নির্বাচিত বিটিএস গুলো লোড করুন
            bts = (await session.execute(select(BTS).where(BTS.id.in_(data.get('bts_ids', []))))).scalars().all()
            
            # মেলা লোড করুন সাথে covered_bts relationship
            m = await session.get(Mela, data['edit_mela_id'], options=[selectinload(Mela.covered_bts)])
            if not m:
                return await callback.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।", show_alert=True)
            
            # বিটিএস আপডেট করুন
            m.covered_bts = bts
            m.location = ", ".join([b.short_address_bn or 'N/A' for b in bts])  # লোকেশন আপডেট (শর্ট এড্রেস)
            
            await session.commit()
            
            # সফল মেসেজ
            await callback.answer("✅ বিটিএস সফলভাবে আপডেট হয়েছে।")
            
            # স্টেট ক্লিয়ার করে মেলা ভিউতে ফিরুন
            await state.clear()
            await render_single_mela_view(callback.message, data['edit_mela_id'], permissions, edit_mode=True, status_text="বিটিএস সফলভাবে আপডেট হয়েছে।")
            
        except Exception as e:
            logger.error(f"BTS only save error: {e}")
            await callback.answer(f"❌ ত্রুটি: {str(e)[:50]}", show_alert=True)

@router.callback_query(F.data == "msave_rso_only")
async def save_rso_only(callback: CallbackQuery, state: FSMContext, permissions: list):
    """এডিট মোডে শুধুমাত্র আরএসও আপডেট করে সেভ করে"""
    data = await state.get_data()
    if not data.get('is_edit_mode') or not data.get('edit_mela_id'):
        return await callback.answer("❌ এডিট মোডে নেই অথবা মেলা আইডি পাওয়া যায়নি।", show_alert=True)
    
    async with async_session() as session:
        try:
            # নির্বাচিত আরএসও গুলো লোড করুন
            rso_ids = data.get('rso_ids', [])
            rso_objs = (await session.execute(select(FieldForce).where(FieldForce.id.in_(rso_ids)))).scalars().all()
            
            # মেলা লোড করুন সাথে অ্যাসাইনমেন্ট
            m = await session.get(Mela, data['edit_mela_id'], options=[selectinload(Mela.assignments)])
            if not m:
                return await callback.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।", show_alert=True)
            
            # পূর্বের আরএসও অ্যাসাইনমেন্ট ডিলিট করুন
            await session.execute(
                delete(MelaAssignment).where(
                    MelaAssignment.mela_id == m.id,
                    MelaAssignment.role_type == 'RSO'
                )
            )
            
            # নতুন আরএসও অ্যাসাইনমেন্ট যোগ করুন
            assignments = []
            for ff in rso_objs:
                assignments.append(MelaAssignment(mela_id=m.id, retailer_code=ff.assisted_retailer_code, role_type='RSO'))
            if assignments:
                session.add_all(assignments)
            
            await session.commit()
            
            # সফল মেসেজ
            await callback.answer("✅ আরএসও সফলভাবে আপডেট হয়েছে।")
            
            # স্টেট ক্লিয়ার করে মেলা ভিউতে ফিরুন
            await state.clear()
            await render_single_mela_view(callback.message, data['edit_mela_id'], permissions, edit_mode=True, status_text="আরএসও সফলভাবে আপডেট হয়েছে।")
            
        except Exception as e:
            logger.error(f"RSO only save error: {e}")
            await callback.answer(f"❌ ত্রুটি: {str(e)[:50]}", show_alert=True)

@router.callback_query(F.data == "msave_bp_only")
async def save_bp_only(callback: CallbackQuery, state: FSMContext, permissions: list):
    """এডিট মোডে শুধুমাত্র বিপি আপডেট করে সেভ করে"""
    data = await state.get_data()
    if not data.get('is_edit_mode') or not data.get('edit_mela_id'):
        return await callback.answer("❌ এডিট মোডে নেই অথবা মেলা আইডি পাওয়া যায়নি।", show_alert=True)
    
    async with async_session() as session:
        try:
            # নির্বাচিত বিপি গুলো লোড করুন
            bp_ids = data.get('bp_ids', [])
            bp_objs = (await session.execute(select(FieldForce).where(FieldForce.id.in_(bp_ids)))).scalars().all()
            
            # মেলা লোড করুন সাথে অ্যাসাইনমেন্ট
            m = await session.get(Mela, data['edit_mela_id'], options=[selectinload(Mela.assignments)])
            if not m:
                return await callback.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।", show_alert=True)
            
            # পূর্বের বিপি অ্যাসাইনমেন্ট ডিলিট করুন
            await session.execute(
                delete(MelaAssignment).where(
                    MelaAssignment.mela_id == m.id,
                    MelaAssignment.role_type == 'BP'
                )
            )
            
            # নতুন বিপি অ্যাসাইনমেন্ট যোগ করুন
            assignments = []
            for ff in bp_objs:
                assignments.append(MelaAssignment(mela_id=m.id, retailer_code=ff.assisted_retailer_code, role_type='BP'))
            if assignments:
                session.add_all(assignments)
            
            await session.commit()
            
            # সফল মেসেজ
            await callback.answer("✅ বিপি সফলভাবে আপডেট হয়েছে।")
            
            # স্টেট ক্লিয়ার করে মেলা ভিউতে ফিরুন
            await state.clear()
            await render_single_mela_view(callback.message, data['edit_mela_id'], permissions, edit_mode=True, status_text="বিপি সফলভাবে আপডেট হয়েছে।")
            
        except Exception as e:
            logger.error(f"BP only save error: {e}")
            await callback.answer(f"❌ ত্রুটি: {str(e)[:50]}", show_alert=True)

@router.callback_query(F.data.startswith("melaedit:"))
async def show_mela_edit_menu(callback: CallbackQuery):
    m_id = int(callback.data.split(":")[1])
    builder = InlineKeyboardBuilder()
    opts = [("📅 তারিখ", "date"), ("🏗 ধরণ", "type"), ("🎯 কাজ", "act"), ("📡 বিটিএস/থানা", "bts"), ("👤 আরএসও", "rso"), ("👷‍♂️ বিপি", "bp"), ("🏬 রিটেইলার", "ret")]
    for l, k in opts: builder.button(text=l, callback_data=f"mfield:{k}:{m_id}")
    builder.button(text="🔙 প্রোফাইলে ফিরুন", callback_data=f"mview_{m_id}")
    await callback.message.edit_text("🛠 <b>কোন তথ্যটি পরিবর্তন করবেন?</b>", reply_markup=builder.adjust(2).as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mfield:"))
async def handle_edit_step(callback: CallbackQuery, state: FSMContext, permissions: list):
    _, field, m_id = callback.data.split(":")
    m_id = int(m_id)
    async with async_session() as session:
        m = await session.get(
            Mela,
            m_id,
            options=[
                selectinload(Mela.covered_bts),
                selectinload(Mela.assignments),
                selectinload(Mela.mela_type),
                selectinload(Mela.mela_activity),
                selectinload(Mela.house)
            ]
        )
        rso_codes = [a.retailer_code for a in m.assignments if a.role_type == 'RSO']
        bp_codes = [a.retailer_code for a in m.assignments if a.role_type == 'BP']
        sso_codes = [a.retailer_code for a in m.assignments if a.role_type == 'SSO']
        rso_ids = (await session.execute(select(FieldForce.id).where(FieldForce.assisted_retailer_code.in_(rso_codes)))).scalars().all() if rso_codes else []
        bp_ids = (await session.execute(select(FieldForce.id).where(FieldForce.assisted_retailer_code.in_(bp_codes)))).scalars().all() if bp_codes else []
        ret_ids = (await session.execute(select(Retailer.id).where(Retailer.retailer_code.in_(sso_codes)))).scalars().all() if sso_codes else []

        await state.update_data(
            house_id=m.house_id,
            h_name=m.house.name if m.house else "N/A",
            edit_mela_id=m.id,
            is_edit_mode=True,
            permissions=permissions,
            date_obj=m.activity_date,
            t_id=m.mela_type_id,
            a_id=m.mela_activity_id,
            th_name=m.thana,
            bts_ids=[b.id for b in m.covered_bts],
            rso_ids=list(rso_ids),
            bp_ids=list(bp_ids),
            ret_ids=list(ret_ids),
            bts_offset=0,
            ret_offset=0
        )
        
        if field == "date":
            await state.set_state(MelaWizard.activity_date)
            await callback.message.answer(
                f"📅 <b>তারিখ পরিবর্তন</b>\nবর্তমান: <code>{m.activity_date.strftime('%d-%m-%Y') if m.activity_date else 'N/A'}</code>\nনতুন তারিখ দিন (DD-MM-YYYY):",
                parse_mode="HTML"
            )
        elif field == "bts":
            await show_bts_multi(callback, state)
        elif field == "rso":
            await show_rso_multi(callback, state)
        elif field == "bp":
            await show_bp_multi(callback, state)
        elif field == "ret":
            await show_ret_multi(callback, state)
        elif field in ["type", "act"]:
            model = MelaType if field == "type" else MelaActivity
            options = (await session.execute(select(model))).scalars().all()
            builder = InlineKeyboardBuilder()
            for opt in options: builder.button(text=opt.name, callback_data=f"msav_edit:{field}:{opt.id}:{m_id}")
            current_name = m.mela_type.name if field == "type" else m.mela_activity.name
            label = "ধরণ" if field == "type" else "কাজ"
            icon = "🏗" if field == "type" else "🎯"
            await callback.message.edit_text(
                f"{icon} <b>{label} পরিবর্তন</b>\nবর্তমান: <b>{current_name}</b>\nনতুনটি বেছে নিন:",
                reply_markup=builder.adjust(1).as_markup(),
                parse_mode="HTML"
            )
    await callback.answer()

@router.callback_query(F.data.startswith("msav_edit:"))
async def save_mela_dropdown_edit(callback: CallbackQuery, state: FSMContext, permissions: list):
    _, field, opt_id, m_id = callback.data.split(":")
    m_id = int(m_id)
    async with async_session() as session:
        m = await session.get(Mela, m_id)
        if not m:
            return await callback.answer("❌ মেলাটি খুঁজে পাওয়া যায়নি।", show_alert=True)
        if field == "type":
            m.mela_type_id = int(opt_id)
        elif field == "act":
            m.mela_activity_id = int(opt_id)
        await session.commit()
    await state.clear()
    await callback.answer("✅ সফলভাবে আপডেট হয়েছে।")
    await render_single_mela_view(callback.message, m_id, permissions, edit_mode=True, status_text="মেলাটি সফলভাবে আপডেট হয়েছে।")

@router.callback_query(F.data.startswith("mela_list_"))
async def list_melas_pagi(callback: CallbackQuery, permissions: list):
    parts = callback.data.split("_")
    house_id, offset = int(parts[2]), int(parts[3])
    now = datetime.now()
    month_start = now.replace(day=1).date()
    if now.month == 12:
        next_month_start = now.replace(year=now.year + 1, month=1, day=1).date()
    else:
        next_month_start = now.replace(month=now.month + 1, day=1).date()

    async with async_session() as session:
        base_filter = and_(
            Mela.house_id == house_id,
            Mela.activity_date >= month_start,
            Mela.activity_date < next_month_start
        )
        total = await session.scalar(select(func.count(Mela.id)).where(base_filter))
        res = await session.execute(
            select(Mela)
            .where(base_filter)
            .order_by(Mela.activity_date.desc())
            .limit(5)
            .offset(offset)
        )
        items = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for m in items:
            thana_name = m.thana or "N/A"
            builder.button(text=f"📅 {m.activity_date.strftime('%d-%m-%Y')} - {thana_name}", callback_data=f"mview_{m.id}")
        builder.adjust(1)
        nav = []
        if offset > 0: nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"mela_list_{house_id}_{offset-5}"))
        if offset + 5 < total: nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"mela_list_{house_id}_{offset+5}"))
        if nav: builder.row(*nav)
        builder.row(InlineKeyboardButton(text="🔙 মেনু", callback_data=f"mela_hsel_{house_id}"))
        await callback.message.edit_text(f"📋 <b>মেলার তালিকা</b> ({bn_num(total)}টি):", reply_markup=builder.as_markup(), parse_mode="HTML")

# --- মেলা অনুসন্ধান ---
@router.callback_query(F.data.startswith("mela_search_"))
async def mela_search_start(callback: CallbackQuery, state: FSMContext):
    """ইউজার যখন মেলা সার্চ বাটনে ক্লিক করবে"""
    house_id = int(callback.data.split("_")[2])
    
    # বাতিলের জন্য একটি বাটন
    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ বাতিল করুন", callback_data=f"mela_list_{house_id}_0")
    
    await callback.message.answer(
        "🔍 <b>মেলা অনুসন্ধান</b>\n\n"
        "যেকোনো তথ্য লিখে পাঠান:\n"
        "• তারিখ (DD‑MM‑YYYY)\n"
        "• বিটিএস কোড\n"
        "• লোকেশন (শর্ট এড্রেস)\n"
        "• আরএসও/বিপি/রিটেইলার কোড\n"
        "• থানা নাম",
        reply_markup=cancel_kb.as_markup(),
        parse_mode="HTML"
    )
    
    # ইউজারকে সার্চ কুয়েরি ইনপুট নেওয়ার স্টেটে নিয়ে যাওয়া ✅
    await state.set_state(MelaSearchState.query)
    await state.update_data(house_id=house_id)
    await callback.answer()

@router.message(MelaSearchState.query)
async def mela_search_process(message: Message, state: FSMContext, permissions: list):
    """মেলা সার্চ প্রসেসিং"""
    query_text = message.text.strip()
    
    # স্টেট থেকে হাউজ আইডি নেওয়া
    data = await state.get_data()
    house_id = data.get('house_id')
    
    if not house_id:
        return await message.answer("❌ সেশন আউট! অনুগ্রহ করে আবার হাউজ সিলেক্ট করে সার্চ করুন।")
    
    if len(query_text) < 2:
        return await message.answer("⚠️ অন্তত ২ অক্ষরের কোড, নাম বা তারিখ লিখে পাঠান।")
    
    async with async_session() as session:
        # তারিখ ফরম্যাট চেক (DD-MM-YYYY)
        date_obj = None
        try:
            date_obj = datetime.strptime(query_text, "%d-%m-%Y").date()
        except ValueError:
            pass
        
        # সার্চ প্যাটার্ন তৈরি
        search_pattern = f"%{query_text}%"
        
        # বেস কুয়েরি: বর্তমান হাউজের মেলা
        base_query = select(Mela).where(Mela.house_id == house_id)
        
        # বিভিন্ন ফিল্ডে সার্চ
        conditions = []
        
        # তারিখ ম্যাচ
        if date_obj:
            conditions.append(Mela.activity_date == date_obj)
        
        # থানা নামে সার্চ
        conditions.append(Mela.thana.ilike(search_pattern))
        
        # লোকেশনে সার্চ (শর্ট এড্রেস)
        conditions.append(Mela.location.ilike(search_pattern))
        
        # বিটিএস কোডে সার্চ (covered_bts এর মাধ্যমে)
        bts_subquery = select(mela_bts_link.c.mela_id).join(
            BTS, BTS.id == mela_bts_link.c.bts_id
        ).where(
            BTS.bts_code.ilike(search_pattern)
        )
        conditions.append(Mela.id.in_(bts_subquery))
        
        # আরএসও/বিপি/রিটেইলার কোডে সার্চ (assignments এর মাধ্যমে)
        assignment_subquery = select(MelaAssignment.mela_id).where(
            MelaAssignment.retailer_code.ilike(search_pattern)
        )
        conditions.append(Mela.id.in_(assignment_subquery))
        
        # মেলার ধরণ বা এক্টিভিটি নামে সার্চ
        mela_type_subquery = select(Mela.id).join(MelaType).where(
            MelaType.name.ilike(search_pattern)
        )
        conditions.append(Mela.id.in_(mela_type_subquery))
        
        mela_activity_subquery = select(Mela.id).join(MelaActivity).where(
            MelaActivity.name.ilike(search_pattern)
        )
        conditions.append(Mela.id.in_(mela_activity_subquery))
        
        # সব কন্ডিশন OR দিয়ে যুক্ত করা
        if conditions:
            base_query = base_query.where(or_(*conditions))
        
        # রেজাল্ট লিমিট করা
        base_query = base_query.order_by(Mela.activity_date.desc()).limit(20)
        
        res = await session.execute(base_query.options(
            selectinload(Mela.mela_type),
            selectinload(Mela.mela_activity),
            selectinload(Mela.house)
        ))
        melas = res.scalars().all()
        
        if not melas:
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 আবার চেষ্টা করুন", callback_data=f"mela_search_{house_id}")
            builder.button(text="🔙 মেনু", callback_data=f"mela_list_{house_id}_0")
            return await message.answer(
                f"❌ '{query_text}' অনুসারে কোনো মেলা পাওয়া যায়নি।",
                reply_markup=builder.adjust(1).as_markup()
            )
        
        # রেজাল্ট লিস্ট তৈরি করা বাটন আকারে
        builder = InlineKeyboardBuilder()
        for m in melas:
            date_str = m.activity_date.strftime("%d-%m-%Y") if m.activity_date else "N/A"
            type_name = m.mela_type.name if m.mela_type else "N/A"
            builder.button(
                text=f"🎪 {date_str} - {type_name} ({m.thana or 'N/A'})",
                callback_data=f"mview_{m.id}"
            )
        
        builder.button(text="🔍 নতুন সার্চ", callback_data=f"mela_search_{house_id}")
        builder.button(text="🔙 মেনু", callback_data=f"mela_list_{house_id}_0")
        builder.adjust(1)
        
        await message.answer(
            f"✅ <b>সার্চ রেজাল্ট:</b> ({bn_num(len(melas))}টি মেলা পাওয়া গেছে)\nবিস্তারিত দেখতে নিচের বাটনে ক্লিক করুন:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    # সার্চ স্টেট ক্লিয়ার করা
    await state.set_state(None)

@router.callback_query(F.data.startswith("mview_"))
async def view_mela_from_list(callback: CallbackQuery, permissions: list):
    m_id = int(callback.data.split("_")[1])
    await render_single_mela_view(callback.message, m_id, permissions, edit_mode=True, status_text="")
    await callback.answer()

@router.callback_query(F.data.startswith("mdel_conf_"))
async def confirm_mela_del(callback: CallbackQuery):
    m_id = int(callback.data.split("_")[2])
    builder = InlineKeyboardBuilder().button(text="✅ নিশ্চিত ডিলিট", callback_data=f"mdel_f_{m_id}").button(text="❌ বাতিল", callback_data=f"mview_{m_id}").adjust(1)
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে এই মেলাটি ডিলিট করতে চান?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("mdel_f_"))
async def final_mela_del(callback: CallbackQuery, permissions: list):
    m_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        m = await session.get(Mela, m_id)
        if m: 
            h_id = m.house_id
            await session.delete(m); await session.commit()
            await callback.answer("🗑 ডিলিট সম্পন্ন"); await render_mela_dashboard(callback.message, h_id, permissions, edit_mode=True)
