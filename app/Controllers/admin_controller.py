from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.role import Role
from app.Views.keyboards.reply import get_admin_main_menu, get_house_mgmt_menu, get_settings_menu
from app.Models.house import House
from app.Models.user import User
from app.Services.db_service import async_session
from config.settings import SUPER_ADMIN_ID

router = Router()

async def get_role_keyboard():
    async with async_session() as session:
        res = await session.execute(select(Role))
        roles = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for r in roles:
            builder.button(text=r.name, callback_data=f"setrole_{r.id}")
        return builder.as_markup()


class HouseCreateForm(StatesGroup):
    name = State()
    code = State()
    cluster = State()
    region = State()
    email = State()
    address = State()
    contact = State()

# ইউজার তৈরির জন্য নতুন FSM স্টেট
class UserCreateForm(StatesGroup):
    telegram_id = State()
    name = State()
    phone = State()
    house_code = State()
    role_id = State()


# --- ১. স্টার্ট কমান্ড এবং নেভিগেশন ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear() # যেকোনো চলমান প্রসেস ক্লিয়ার করবে
    user_id = message.from_user.id

    # ১. সুপার এডমিন চেক (সবার আগে)
    if int(user_id) == int(SUPER_ADMIN_ID):
        # return দেওয়ার মানে হলো এই মেসেজটি পাঠিয়ে কোড এখানেই থেমে যাবে
        return await message.answer(
            "👋 স্বাগতম সুপার এডমিন! ❤️",
            reply_markup=get_admin_main_menu()
        )

    # ২. ডাটাবেজে ইউজার রেজিস্টার্ড কি না চেক করা
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user:
            # যদি ইউজার পাওয়া যায়, মেসেজ পাঠিয়ে এখানেই শেষ হবে (return)
            return await message.answer(
                f"👋 স্বাগতম {db_user.name}!\nআপনার অ্যাকাউন্টটি সক্রিয় আছে।"
            )

    # ৩. যদি উপরের কোনোটিই না হয় (অচেনা ইউজার), শুধুমাত্র তখনই নিচের মেসেজটি যাবে
    await message.answer(
        f"আপনার আইডি: `{user_id}`\n"
        "অনুগৃহ করে এই আইডি সুপার এডমিনকে দিন, যাতে আপনাকে সিস্টেমে যুক্ত করা যায়।",
        parse_mode="Markdown"
    )


@router.message(F.text == "🏠 হাউজ ম্যানেজমেন্ট")
async def house_mgmt_menu(message: Message):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer("🏢 হাউজ ম্যানেজমেন্ট অপশন:", reply_markup=get_house_mgmt_menu())

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer("প্রধান মেনু:", reply_markup=get_admin_main_menu())

@router.message(F.text == "👤 ইউজার ম্যানেজমেন্ট")
async def user_mgmt_menu(message: Message):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        # একটি সাব-মেনু কিবোর্ড (নিচে reply.py তে এটি তৈরি করতে হবে)
        from app.Views.keyboards.reply import get_user_mgmt_menu
        await message.answer("👤 ইউজার ম্যানেজমেন্ট অপশনসমূহ:", reply_markup=get_user_mgmt_menu())

@router.message(F.text == "⚙️ সেটিংস")
async def settings_menu(message: Message):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer(
            f"⚙️ **সিস্টেম সেটিংস**\n\n"
            f"👑 সুপার এডমিন আইডি: `{SUPER_ADMIN_ID}`\n"
            f"🤖 বট স্ট্যাটাস: অনলাইন ✅\n"
            f"📅 আজকের তারিখ: {datetime.now().strftime('%d-%m-%Y')}",
            reply_markup=get_settings_menu(),
            parse_mode="Markdown"
        )
# --- ২. হাউজ তৈরির ধাপসমূহ ---

@router.message(F.text == "➕ নতুন হাউজ তৈরি")
async def start_house_creation(message: Message, state: FSMContext):
    if int(message.from_user.id) != int(SUPER_ADMIN_ID): return
    await message.answer("হাউজের নাম লিখুন:")
    await state.set_state(HouseCreateForm.name)


@router.message(HouseCreateForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("হাউজ কোড (Code) লিখুন: (উদা: MYMVAI01)")
    await state.set_state(HouseCreateForm.code)


@router.message(HouseCreateForm.code)
async def process_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text)
    await message.answer("ক্লাস্টার (Cluster) লিখুন: (উদা: East)")
    await state.set_state(HouseCreateForm.cluster)


@router.message(HouseCreateForm.cluster)
async def process_cluster(message: Message, state: FSMContext):
    await state.update_data(cluster=message.text)
    await message.answer("রিজিয়ন (Region) লিখুন: (উদা: Brahmanbaria)")
    await state.set_state(HouseCreateForm.region)


@router.message(HouseCreateForm.region)
async def process_region(message: Message, state: FSMContext):
    await state.update_data(region=message.text)
    await message.answer("ইমেইল (Email) লিখুন:")
    await state.set_state(HouseCreateForm.email)


@router.message(HouseCreateForm.email)
async def process_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text)
    await message.answer("ঠিকানা (Address) লিখুন:")
    await state.set_state(HouseCreateForm.address)


@router.message(HouseCreateForm.address)
async def process_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("কন্টাক্ট নাম্বার (Contact) লিখুন:")
    await state.set_state(HouseCreateForm.contact)


@router.message(HouseCreateForm.contact)
async def save_house_final(message: Message, state: FSMContext):
    data = await state.get_data()
    contact = message.text
    sub_end_date = datetime.now() + timedelta(days=30)

    async with async_session() as session:
        new_house = House(
            name=data['name'],
            code=data['code'],
            cluster=data['cluster'],
            region=data['region'],
            email=data['email'],
            address=data['address'],
            contact=contact,
            subscription_date=sub_end_date
        )
        session.add(new_house)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ হাউজ তৈরি সফল হয়েছে!\n\n"
        f"🏠 নাম: {data['name']}\n"
        f"🔑 কোড: {data['code']}\n"
        f"📅 মেয়াদ শেষ: {sub_end_date.strftime('%d-%m-%Y')}",
        reply_markup=get_house_mgmt_menu()
    )


# --- ২. নতুন ইউজার তৈরির ধাপসমূহ ---
@router.message(F.text == "📋 ইউজার লিস্ট দেখুন")
async def show_user_list(message: Message):
    if int(message.from_user.id) != SUPER_ADMIN_ID: return None


    async with async_session() as session:
        # selectinload ব্যবহার করা হয়েছে যাতে ইউজারের সাথে তার রোলের নামও আসে
        result = await session.execute(select(User).options(selectinload(User.roles)))
        users = result.scalars().all()

        if not users:
            return await message.answer("⚠️ বর্তমানে কোনো ইউজার নিবন্ধিত নেই।")

        text = "👥 **নিবন্ধিত ইউজার তালিকা**\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"

        for index, u in enumerate(users, start=1):
            role_names = ", ".join([r.name for r in u.roles]) if u.roles else "রোল নেই"

            text += f"👤 **ইউজার #{index}**\n"
            text += f"🆔 আইডি: `{u.telegram_id}`\n"
            text += f"📛 নাম: {u.name}\n"
            text += f"📞 ফোন: {u.phone_number or 'দেওয়া নেই'}\n"
            text += f"🛠 রোল: {role_names}\n"
            text += "────────────────────\n"

        await message.answer(text, parse_mode="Markdown")
        return None


# --- ১. নতুন ইউজার তৈরি শুরু ---
@router.message(F.text == "➕ নতুন ইউজার তৈরি")
async def start_user_creation(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) != SUPER_ADMIN_ID: return

    async with async_session() as session:
        # সবার আগে চেক: রোল আছে কি না
        res = await session.execute(select(Role))
        roles = res.scalars().all()

        if not roles:
            # রোল না থাকলে মেসেজ এবং সেটিংস মেনু (রোল/পারমিশন তৈরির বাটন) দেখাবে
            from app.Views.keyboards.reply import get_settings_menu
            return await message.answer(
                "⚠️ সিস্টেমে কোনো **রোল (Role)** তৈরি করা নেই!\n"
                "রোল ছাড়া ইউজার তৈরি করা সম্ভব নয়। অনুগ্রহ করে আগে পারমিশন এবং রোল তৈরি করুন।",
                reply_markup=get_settings_menu()
            )

    # রোল থাকলে প্রসেস শুরু হবে
    await message.answer("ইউজারের টেলিগ্রাম আইডি (Telegram ID) লিখুন:")
    await state.set_state(UserCreateForm.telegram_id)


# --- ২. আইডি নেওয়ার পর নাম চাওয়া ---
@router.message(UserCreateForm.telegram_id)
async def process_user_tid(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ভুল আইডি! শুধুমাত্র সংখ্যা লিখুন।")

    await state.update_data(telegram_id=int(message.text))
    await message.answer("ইউজারের নাম লিখুন:")
    await state.set_state(UserCreateForm.name)
    return None


# --- ৩. নাম নেওয়ার পর ফোন নাম্বার চাওয়া ---
@router.message(UserCreateForm.name)
async def process_user_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("ইউজারের ফোন নাম্বার লিখুন:")
    await state.set_state(UserCreateForm.phone)


# --- ৪. ফোন নাম্বার নেওয়ার পর হাউজ কোড চাওয়া ---
@router.message(UserCreateForm.phone)
async def process_user_phone(message: Message, state: FSMContext):
    # ১. ফোন নাম্বার সেভ করা এবং রোলের জন্য একটি খালি লিস্ট স্টেট-এ রাখা
    await state.update_data(phone=message.text, selected_roles=[])

    async with async_session() as session:
        # ২. ডাটাবেজ থেকে সব রোল চেক করা
        res = await session.execute(select(Role))
        roles = res.scalars().all()

        # ৩. যদি কোনো রোল তৈরি করা না থাকে
        if not roles:
            await state.clear()
            # সেটিংস মেনু রিটার্ন করা যাতে সুপার এডমিন রোল তৈরি করতে পারে
            from app.Views.keyboards.reply import get_settings_menu
            return await message.answer(
                "⚠️ সিস্টেমে কোনো **রোল (Role)** তৈরি করা নেই!\n"
                "রোল ছাড়া ইউজার তৈরি করা সম্ভব নয়। অনুগ্রহ করে আগে পারমিশন এবং রোল তৈরি করুন।",
                reply_markup=get_settings_menu(),
                parse_mode="Markdown"
            )

        # ৪. রোল থাকলে মাল্টি-সিলেকশন কিবোর্ড তৈরি করা
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        for r in roles:
            # শুরুতে সব রোলের পাশে '🔘' থাকবে
            builder.button(text=f"🔘 {r.name}", callback_data=f"toggle_user_role_{r.id}")

        # ৫. সিলেকশন শেষ করার জন্য 'সেভ' বাটন যোগ করা
        builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
        builder.adjust(2)  # প্রতি লাইনে ২টা বাটন

        await message.answer(
            "ইউজারের জন্য এক বা একাধিক রোল সিলেক্ট করুন:\n"
            "(সিলেক্ট করতে রোলের ওপর ক্লিক করুন)",
            reply_markup=builder.as_markup()
        )

        # ৬. স্টেট পরিবর্তন করে পরবর্তী স্টেপের জন্য প্রস্তুত করা
        await state.set_state(UserCreateForm.role_id)


# ২. রোল টগল হ্যান্ডেলার (টিক চিহ্নের জন্য)
@router.callback_query(F.data.startswith("toggle_user_role_"))
async def toggle_user_role(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_roles", [])

    if role_id in selected:
        selected.remove(role_id)
    else:
        selected.append(role_id)

    await state.update_data(selected_roles=selected)

    async with async_session() as session:
        res = await session.execute(select(Role))
        all_roles = res.scalars().all()
        builder = InlineKeyboardBuilder()
        for r in all_roles:
            status = "✅" if r.id in selected else "🔘"
            builder.button(text=f"{status} {r.name}", callback_data=f"toggle_user_role_{r.id}")
        builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()


# ফাইনাল সেভ লজিক (রোল রিলেশনসহ)
@router.callback_query(F.data == "save_user_roles")
async def save_user_roles_step(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_roles = data.get("selected_roles", [])

    if not selected_roles:
        return await callback.answer("⚠️ অন্তত একটি রোল সিলেক্ট করুন!", show_alert=True)

    # পরের ধাপে নিয়ে যাওয়া
    await callback.message.answer("হাউজ কোড (House Code) লিখুন: (যার সাথে ইউজারকে যুক্ত করবেন)")
    await state.set_state(UserCreateForm.house_code)
    await callback.answer()




@router.callback_query(F.data.startswith("setrole_"))
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[1])
    await state.update_data(role_id=role_id)
    await callback.message.answer("হাউজ কোড (House Code) লিখুন:")
    await state.set_state(UserCreateForm.house_code)


# --- ৫. ফাইনাল ধাপ: ডাটাবেজে সেভ করা ---
@router.message(UserCreateForm.house_code)
async def save_user_final(message: Message, state: FSMContext):
    data = await state.get_data()
    house_code = message.text
    role_ids = data.get('selected_roles', [])

    async with async_session() as session:
        # ১. হাউজ চেক করা
        house_res = await session.execute(select(House).where(House.code == house_code))
        house = house_res.scalar_one_or_none()

        if not house:
            return await message.answer(f"❌ '{house_code}' কোডওয়ালা কোনো হাউজ পাওয়া যায়নি। সঠিক কোড দিন।")

        # ২. সিলেক্ট করা রোল অবজেক্টগুলো ডাটাবেজ থেকে নিয়ে আসা
        roles_res = await session.execute(select(Role).where(Role.id.in_(role_ids)))
        roles_list = roles_res.scalars().all()

        # ৩. নতুন ইউজার তৈরি ও রোল অ্যাসাইন করা
        new_user = User(
            telegram_id=data['telegram_id'],
            name=data['name'],
            phone_number=data['phone'],
            # roles হচ্ছে relationship, এখানে আমরা অবজেক্টের লিস্ট পাস করছি
            roles=roles_list
        )

        session.add(new_user)
        await session.commit()

    # রোলের নামগুলো সুন্দরভাবে দেখানোর জন্য
    role_names = ", ".join([r.name for r in roles_list])

    await state.clear()
    await message.answer(
        f"✅ ইউজার সফলভাবে তৈরি হয়েছে!\n\n"
        f"👤 নাম: {data['name']}\n"
        f"🆔 আইডি: `{data['telegram_id']}`\n"
        f"📞 ফোন: {data['phone']}\n"
        f"🎭 রোলস: {role_names}\n"
        f"🏠 হাউজ: {house.name}",
        parse_mode="Markdown"
    )
    return None


# --- ৩. সাবস্ক্রিপশন রিনিউ কমান্ড ---

@router.message(Command("renew"))
async def renew_subscription(message: Message, command: CommandObject):
    if int(message.from_user.id) != int(SUPER_ADMIN_ID):
        return await message.answer("আপনার এই কমান্ড ব্যবহারের অনুমতি নেই।")

    if not command.args:
        return await message.answer("ব্যবহার পদ্ধতি: `/renew <হাউজ_কোড> <দিন]`", parse_mode="Markdown")

    try:
        args = command.args.split()
        house_code = args[0]
        days_to_add = int(args[1])

        async with async_session() as session:
            result = await session.execute(select(House).where(House.code == house_code))
            house = result.scalar_one_or_none()

            if not house:
                return await message.answer(f"❌ কোড `{house_code}` পাওয়া যায়নি।")

            current_expiry = house.subscription_date or datetime.now()
            base_date = max(current_expiry, datetime.now())
            new_expiry = base_date + timedelta(days=days_to_add)

            house.subscription_date = new_expiry
            await session.commit()

            await message.answer(
                f"✅ **সাবস্ক্রিপশন রিনিউ সফল!**\n\n"
                f"🏠 হাউজ: {house.name}\n"
                f"➕ যোগ করা হয়েছে: {days_to_add} দিন\n"
                f"📅 নতুন মেয়াদ: {new_expiry.strftime('%d-%m-%Y')}",
                parse_mode="Markdown"
            )
            return None

            # await message.answer(f"✅ রিনিউ সফল! নতুন মেয়াদ: {new_expiry.strftime('%d-%m-%Y')}")
    except Exception as e:
        await message.answer(f"ভুল ফরম্যাট! /renew CODE DAYS")