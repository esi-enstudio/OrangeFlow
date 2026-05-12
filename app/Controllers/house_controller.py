from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandObject
from sqlalchemy import select, func
from app.Models.house import House
from app.Services.db_service import async_session
from app.Views.keyboards.reply import get_house_mgmt_menu
from app.Views.keyboards.inline import get_house_pagination_kb, get_house_action_kb, get_house_edit_fields_kb
from app.Views.keyboards.reply import get_admin_main_menu
from config.settings import SUPER_ADMIN_ID

router = Router()

# --- FSM States ---
class HouseCreateForm(StatesGroup):
    name, code, cluster, region, email, address, contact, dms_user, dms_pass, dms_house_id = State(), State(), State(), State(), State(), State(), State(), State(), State(), State()

class HouseSearchState(StatesGroup): code = State()
class HouseUpdateState(StatesGroup): house_id, field, value = State(), State(), State()


# --- ১. হাউজ ম্যানেজমেন্ট মেইন মেনু ---
@router.message(F.text == "🏠 হাউজ ম্যানেজমেন্ট", flags={"permission": "view_houses"})
async def house_mgmt_menu(message: Message, permissions: list):
    await message.answer(
        "🏢 হাউজ ম্যানেজমেন্ট অপশন:",
        reply_markup=get_house_mgmt_menu(permissions)
    )

# --- ২. নতুন হাউজ তৈরি (FSM Flow) ---
@router.message(F.text == "➕ নতুন হাউজ তৈরি", flags={"permission": "create_house"})
async def start_house_creation(message: Message, state: FSMContext):
    await message.answer("হাউজের নাম লিখুন:")
    await state.set_state(HouseCreateForm.name)

@router.message(HouseCreateForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("হাউজ কোড লিখুন: (উদা: MYMVAI01)")
    await state.set_state(HouseCreateForm.code)

@router.message(HouseCreateForm.code)
async def process_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text)
    await message.answer("ক্লাস্টার লিখুন:")
    await state.set_state(HouseCreateForm.cluster)

@router.message(HouseCreateForm.cluster)
async def process_cluster(message: Message, state: FSMContext):
    await state.update_data(cluster=message.text)
    await message.answer("রিজিয়ন লিখুন:")
    await state.set_state(HouseCreateForm.region)

@router.message(HouseCreateForm.region)
async def process_region(message: Message, state: FSMContext):
    await state.update_data(region=message.text)
    await message.answer("ইমেইল লিখুন:")
    await state.set_state(HouseCreateForm.email)

@router.message(HouseCreateForm.email)
async def process_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text)
    await message.answer("ঠিকানা লিখুন:")
    await state.set_state(HouseCreateForm.address)

@router.message(HouseCreateForm.address)
async def process_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("কন্টাক্ট নাম্বার লিখুন:")
    await state.set_state(HouseCreateForm.contact)

@router.message(HouseCreateForm.contact)
async def process_house_contact(message: Message, state: FSMContext):
    await state.update_data(contact=message.text)
    await message.answer("ডিএমএস ইউজারনেম (DMS Username) লিখুন:")
    await state.set_state(HouseCreateForm.dms_user)

@router.message(HouseCreateForm.dms_user)
async def process_dms_user(message: Message, state: FSMContext):
    await state.update_data(dms_user=message.text)
    await message.answer("ডিএমএস পাসওয়ার্ড (DMS Password) লিখুন:")
    await state.set_state(HouseCreateForm.dms_pass)

@router.message(HouseCreateForm.dms_pass)
async def process_dms_pass(message: Message, state: FSMContext):
    await state.update_data(dms_pass=message.text)
    await message.answer("ডিএমএস হাউজ আইডি (DMS House ID) লিখুন:")
    await state.set_state(HouseCreateForm.dms_house_id)

# ফাইনাল সেভ
@router.message(HouseCreateForm.dms_house_id)
async def save_house_final(message: Message, state: FSMContext, permissions: list):
    data = await state.get_data()
    dms_house_id = message.text
    sub_end_date = datetime.now() + timedelta(days=30)

    async with async_session() as session:
        new_house = House(
            name=data['name'],
            code=data['code'],
            cluster=data['cluster'],
            region=data['region'],
            email=data['email'],
            address=data['address'],
            contact=data['contact'],
            dms_user=data['dms_user'],
            dms_pass=data['dms_pass'],
            dms_house_id=dms_house_id,
            subscription_date=sub_end_date
        )
        session.add(new_house)
        await session.commit()

    await message.answer(
        f"✅ হাউজটি সফলভাবে তৈরি হয়েছে: {data['name']}",
        reply_markup=get_house_mgmt_menu(permissions)
    )
    await state.clear()

# --- ৩. হাউজ লিস্ট (Pagination) ---
@router.message(F.text == "📋 হাউজ লিস্ট দেখুন", flags={"permission": "view_houses"})
async def show_house_list(message: Message, page: int = 1):
    limit = 5
    offset = (page - 1) * limit
    async with async_session() as session:
        total = await session.scalar(select(func.count(House.id)))
        total_pages = (total + limit - 1) // limit
        res = await session.execute(select(House).order_by(House.id).offset(offset).limit(limit))
        houses = res.scalars().all()
        await message.answer(f"🏢 হাউজ তালিকা (পেজ: {page}/{total_pages}):",
                             reply_markup=get_house_pagination_kb(houses, page, total_pages))

@router.callback_query(F.data.startswith("hlist_page_"))
async def handle_pagination(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await callback.message.delete()
    await show_house_list(callback.message, page)

# --- কমন হেল্পার ফাংশন (তথ্য রেন্ডার করার জন্য) ---
async def render_house_details(callback: CallbackQuery, house_id: int):
    async with async_session() as session:
        h = await session.get(House, house_id)
        if not h:
            return await callback.answer("⚠️ হাউজটি পাওয়া যায়নি।", show_alert=True)

        from app.Utils.helpers import get_house_full_profile_text
        details = get_house_full_profile_text(h)

        await callback.message.edit_text(
            details,
            reply_markup=get_house_action_kb(h.id, h.is_active),
            parse_mode="HTML"
        )


# --- বিস্তারিত বাটন হ্যান্ডেলার (লিস্ট থেকে) ---
@router.callback_query(F.data.startswith("view_h_"))
async def view_details_handler(callback: CallbackQuery):
    h_id = int(callback.data.split("_")[2])
    await render_house_details(callback, h_id)
    await callback.answer()

# --- একটিভ/ডি-একটিভ টগল হ্যান্ডেলার ---
@router.callback_query(F.data.startswith("toggle_h_status_"))
async def toggle_status(callback: CallbackQuery):
    h_id = int(callback.data.split("_")[3])

    async with async_session() as session:
        h = await session.get(House, h_id)
        if h:
            h.is_active = not h.is_active
            await session.commit()
            await callback.answer(f"হাউজ এখন {'Active' if h.is_active else 'Deactive'}")
        else:
            await callback.answer("হাউজ পাওয়া যায়নি।", show_alert=True)

    await render_house_details(callback, h_id)


# --- সার্চ শুরু করা ---
@router.callback_query(F.data == "search_house_start")
async def start_house_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔍 হাউজ কোডটি (House Code) লিখুন:\n(উদা: MYMVAI01)")
    await state.set_state(HouseSearchState.code)
    await callback.answer()

# --- সার্চ রেজাল্ট দেখানো ---
@router.message(HouseSearchState.code)
async def process_house_search(message: Message, state: FSMContext):
    search_code = message.text.strip().upper()

    async with async_session() as session:
        result = await session.execute(
            select(House).where(func.upper(House.code) == search_code)
        )
        h = result.scalar_one_or_none()

        if not h:
            return await message.answer(
                f"❌ কোড `{search_code}` দিয়ে কোনো হাউজ পাওয়া যায়নি।\nসঠিক কোডটি পুনরায় লিখুন বা /start দিয়ে ফিরে যান।",
                parse_mode="Markdown"
            )

        await state.clear()

        status = "Active ✅" if h.is_active else "Deactive ❌"
        details = (
            f"🏢 **হাউজ ডিটেইলস (সার্চ রেজাল্ট)** 🔍\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📛 নাম: {h.name}\n"
            f"🔑 কোড: `{h.code}`\n"
            f"🟢 স্ট্যাটাস: {status}\n"
            f"🌍 ক্লাস্টার: {h.cluster}\n"
            f"📍 রিজিয়ন: {h.region}\n"
            f"📧 ইমেইল: {h.email or 'N/A'}\n"
            f"🏠 ঠিকানা: {h.address or 'N/A'}\n"
            f"📞 কন্টাক্ট: {h.contact or 'N/A'}\n"
            f"📅 মেয়াদ শেষ: {h.subscription_date.strftime('%d-%m-%Y')}\n"
            f"────────────────────"
        )

        await message.answer(
            details,
            reply_markup=get_house_action_kb(h.id, h.is_active),
            parse_mode="Markdown"
        )

# --- ১. কোন তথ্যটি আপডেট করতে চান তা দেখানো (মেনু) ---
@router.callback_query(F.data.startswith("edit_h_info_"))
async def show_house_edit_menu(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[3])

    await callback.message.edit_text(
        "🛠 **আপনি হাউজের কোন তথ্যটি আপডেট করতে চান?**",
        reply_markup=get_house_edit_fields_kb(house_id),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- ২. নির্দিষ্ট ফিল্ড সিলেক্ট করা (যেমন: নাম বা কন্টাক্ট) ---
@router.callback_query(F.data.startswith("h_edit_"))
async def process_house_field_selection(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    house_id = int(parts[-1])
    field_name = "_".join(parts[2:-1])

    async with async_session() as session:
        h = await session.get(House, house_id)
        if not h:
            return await callback.answer("❌ হাউজ পাওয়া যায়নি।", show_alert=True)

        current_value = getattr(h, field_name)
        display_value = str(current_value) if current_value and str(current_value).lower() != 'nan' else "দেওয়া নেই"

    field_labels = {
        "name": "নাম", "code": "কোড", "cluster": "ক্লাস্টার",
        "region": "রিজিয়ন", "email": "ইমেইল", "address": "ঠিকানা",
        "contact": "কন্টাক্ট", "dms_user": "DMS ইউজারনেম",
        "dms_pass": "DMS পাসওয়ার্ড", "dms_house_id": "DMS হাউজ আইডি"
    }
    label = field_labels.get(field_name, field_name.replace('_', ' ').capitalize())

    await state.update_data(edit_h_id=house_id, edit_h_field=field_name)

    text = (
        f"📝 **হাউজ তথ্য আপডেট**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 ফিল্ড: **{label}**\n"
        f"📌 বর্তমান তথ্য: `{display_value}`\n\n"
        f"👉 নতুন তথ্যটি লিখে পাঠান (অথবা বাতিল করতে /start দিন):"
    )

    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(HouseUpdateState.value)
    await callback.answer()

# --- ৩. নতুন ভ্যালু সেভ করা এবং ডাটাবেজ আপডেট ---
@router.message(HouseUpdateState.value)
async def save_house_update_final(message: Message, state: FSMContext):
    data = await state.get_data()
    house_id = data.get("edit_h_id")
    field_name = data.get("edit_h_field")
    new_val = message.text.strip()

    if not house_id or not field_name:
        await state.clear()
        return await message.answer("❌ সেশন এরর! অনুগ্রহ করে আবার চেষ্টা করুন।")

    async with async_session() as session:
        h = await session.get(House, house_id)

        if not h:
            await state.clear()
            return await message.answer("❌ এরর: হাউজটি ডাটাবেজে খুঁজে পাওয়া যায়নি।")

        setattr(h, field_name, new_val)
        await session.commit()

        await session.refresh(h)

        from app.Utils.helpers import get_house_full_profile_text
        from app.Views.keyboards.inline import get_house_action_kb

        updated_profile = get_house_full_profile_text(h)

        reply_markup = get_house_action_kb(h.id, h.is_active)

    await state.clear()

    display_field = field_name.replace('_', ' ').upper()
    await message.answer(f"✅ সফলভাবে <b>{display_field}</b> আপডেট করা হয়েছে।", parse_mode="HTML")

    await message.answer(
        updated_profile,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )



# --- ৫. সাবস্ক্রিপশন রিনিউ (শুধু সুপার এডমিন) ---
@router.message(Command("renew"))
async def renew_sub(message: Message, command: CommandObject):
    # সুপার এডমিন নিশ্চিত করা (শতভাগ নিরাপত্তা)
    if message.from_user.id != SUPER_ADMIN_ID:
        return await message.answer("🚫 এই কমান্ড শুধুমাত্র সুপার এডমিন ব্যবহার করতে পারেন।")

    if not command.args:
        return await message.answer(
            "❌ অনুগ্রহ করে হাউজ কোড এবং দিনের সংখ্যা দিন।\n"
            "উদাহরণ: /renew CODE DAYS",
            parse_mode="HTML"
        )

    args = command.args.split()
    if len(args) != 2:
        return await message.answer(
            "❌ ভুল ফরম্যাট! সঠিক ফরম্যাট: /renew CODE DAYS\n"
            "উদাহরণ: /renew MYMVAI01 30",
            parse_mode="HTML"
        )

    house_code = args[0].strip().upper()
    try:
        days = int(args[1])
        if days <= 0:
            return await message.answer("❌ দিনের সংখ্যা অবশ্যই ০ এর বেশি হতে হবে।")
    except ValueError:
        return await message.answer("❌ দিনের সংখ্যা একটি সংখ্যা হতে হবে।")

    try:
        async with async_session() as session:
            from app.Models.subscription import HouseSubscription, SubscriptionRenewal

            h = (await session.execute(select(House).where(House.code == house_code))).scalar_one_or_none()
            if not h:
                return await message.answer(f"❌ হাউজ কোড `{house_code}` দিয়ে কোনো হাউজ পাওয়া যায়নি।")

            now = datetime.now()
            old_end_date = h.subscription_date

            # নতুন তারিখ নির্ধারণ
            if h.subscription_date and h.subscription_date > now:
                new_start = h.subscription_date
                new_end = h.subscription_date + timedelta(days=days)
            else:
                new_start = now
                new_end = now + timedelta(days=days)

            h.subscription_date = new_end

            # সাবস্ক্রিপশন হিস্ট্রি তৈরি করা
            renewal = SubscriptionRenewal(
                subscription_id=None,  # পরে আপডেট হবে
                old_end_date=old_end_date,
                new_start_date=new_start,
                new_end_date=new_end,
                days_added=days,
                renewed_by=message.from_user.id,
                notes=f"ম্যানুয়াল রিনিউ - {days} দিন"
            )

            # যদি আগে থেকে সাবস্ক্রিপশন থাকে তাহলে লিংক করা
            active_sub = (await session.execute(
                select(HouseSubscription)
                .where(HouseSubscription.house_id == h.id)
                .where(HouseSubscription.is_active == True)
                .where(HouseSubscription.end_date >= now)
            )).scalar_one_or_none()

            if active_sub:
                renewal.subscription_id = active_sub.id

            session.add(renewal)
            await session.commit()

            # রিনিউ হিস্ট্রি আইডি আপডেট
            renewal.subscription_id = active_sub.id if active_sub else None
            await session.commit()

            # হাউজের বর্তমান স্ট্যাটাস চেক
            status_emoji = "✅" if new_end > now else "⚠️"
            days_remaining = (new_end - now).days

            await message.answer(
                f"✅ <b>{h.display_name}</b> এর সাবস্ক্রিপশন রিনিউ করা হয়েছে।\n"
                f"📅 নতুন মেয়াদ: <b>{new_end.strftime('%d-%m-%Y')}</b>\n"
                f"📊 অবশিষ্ট দিন: {days_remaining} দিন {status_emoji}\n"
                f"🕐 রিনিউ তথ্য সংরক্ষিত হয়েছে।",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"❌ ত্রুটি: {str(e)}")


# --- ৬. সাবস্ক্রিপশন হিস্ট্রি দেখুন (শুধু সুপার এডমিন) ---
@router.message(Command("subhistory"))
async def show_sub_history(message: Message, command: CommandObject):
    if message.from_user.id != SUPER_ADMIN_ID:
        return await message.answer("🚫 এই কমান্ড শুধুমাত্র সুপার এডমিন ব্যবহার করতে পারেন।")

    if not command.args:
        return await message.answer("❌ হাউজ কোড দিন। উদাহরণ: /subhistory MYMVAI01")

    house_code = command.args.strip().upper()

    try:
        async with async_session() as session:
            from app.Models.subscription import SubscriptionRenewal

            h = (await session.execute(select(House).where(House.code == house_code))).scalar_one_or_none()
            if not h:
                return await message.answer(f"❌ হাউজ কোড `{house_code}` দিয়ে কোনো হাউজ পাওয়া যায়নি।")

            # সর্বশেষ ১০টি রিনিউ রেকর্ড (সব হাউজের)
            renewals = (await session.execute(
                select(SubscriptionRenewal)
                .order_by(SubscriptionRenewal.renewed_at.desc())
                .limit(10)
            )).scalars().all()

            if not renewals:
                return await message.answer(f"📋 কোনো রিনিউ হিস্ট্রি পাওয়া যায়নি।")

            text = f"📜 <b>সাম্প্রতিক রিনিউ হিস্টরি (সর্বশেষ ১০টি)</b>:\n━━━━━━━━━━━━━━━━━━━━\n"
            for r in renewals:
                text += f"📅 {r.new_end_date.strftime('%d-%m-%Y')} | +{r.days_added} দিন | {r.renewed_at.strftime('%d-%m %H:%M')}\n"

            await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ ত্রুটি: {str(e)}")


# --- ৭. সাবস্ক্রিপশন প্যাকেজ লিস্ট (শুধু সুপার এডমিন) ---
@router.message(Command("packages"))
async def show_packages(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return await message.answer("🚫 এই কমান্ড শুধুমাত্র সুপার এডমিন ব্যবহার করতে পারেন।")

    try:
        async with async_session() as session:
            from app.Models.subscription import SubscriptionPackage

            packages = (await session.execute(
                select(SubscriptionPackage).where(SubscriptionPackage.is_active == True)
            )).scalars().all()

            if not packages:
                return await message.answer("❌ কোনো প্যাকেজ পাওয়া যায়নি।")

            text = "📦 <b>সাবস্ক্রিপশন প্যাকেজ সমূহ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for pkg in packages:
                text += f"<b>{pkg.name}</b> ({pkg.tier.value.upper()})\n"
                text += f"💰 দাম: ৳{pkg.price:,.0f}/মাস\n"
                text += f"📅 মেয়াদ: {pkg.duration_days} দিন\n"
                text += f"📝 {pkg.description}\n"
                text += f"✨ ফিচার: {pkg.features}\n"
                text += "━━━━━━━━━━━━━━━━━━━━\n"

            await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ ত্রুটি: {str(e)}")