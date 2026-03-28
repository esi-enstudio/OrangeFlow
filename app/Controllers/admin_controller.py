import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandObject
from sqlalchemy import select

from app.Models.house import House
from app.Models.user import User
from app.Services.db_service import async_session
from app.Views.keyboards.reply import get_admin_main_menu, get_house_mgmt_menu, get_settings_menu
from config.settings import SUPER_ADMIN_ID

router = Router()

# ==========================================
# 1. FSM STATES (ফরম ডিক্লারেশন)
# ==========================================

class HouseCreateForm(StatesGroup):
    name = State()
    code = State()
    cluster = State()
    region = State()
    email = State()
    address = State()
    contact = State()


# ==========================================
# 3. CORE NAVIGATION (প্রধান মেনু ও নেভিগেশন)
# ==========================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if int(user_id) == int(SUPER_ADMIN_ID):
        return await message.answer("👋 স্বাগতম সুপার এডমিন! ❤️", reply_markup=get_admin_main_menu())

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user:
            # যদি ইউজার পাওয়া যায়, মেসেজ পাঠিয়ে এখানেই শেষ হবে (return)
            return await message.answer(
                f"👋 স্বাগতম {db_user.name}!\nআপনার অ্যাকাউন্টটি সক্রিয় আছে।"
            )

    await message.answer(
        f"আপনার আইডি: `{user_id}`\nঅনুগ্রহ করে এই আইডি এডমিনকে দিন।",
        parse_mode="Markdown"
    )

@router.message(F.text == "🏠 হাউজ ম্যানেজমেন্ট", flags={"permission": "view_houses"})
async def house_mgmt_menu(message: Message):
    await message.answer("🏢 হাউজ ম্যানেজমেন্ট অপশন:", reply_markup=get_house_mgmt_menu())


# ==========================================
# 6. HOUSE MANAGEMENT (হাউজ ও সাবস্ক্রিপশন)
# ==========================================

@router.message(F.text == "➕ নতুন হাউজ তৈরি", flags={"permission": "create_house"})
async def start_house_creation(message: Message, state: FSMContext):
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



# --- সাবস্ক্রিপশন রিনিউ কমান্ড ---
@router.message(Command("renew"), flags={"permission": "renew_subscription"})
async def renew_subscription(message: Message, command: CommandObject):
    if int(message.from_user.id) != SUPER_ADMIN_ID:
        return await message.answer("আপনার এই কমান্ড ব্যবহারের অনুমতি নেই।")
    
    if not command.args: return await message.answer("উদা: `/renew CODE DAYS`", parse_mode="Markdown")
    try:
        args = command.args.split()
        house_code = args[0]
        days_to_add = int(args[1])

        async with async_session() as session:
            h = (await session.execute(select(House).where(House.code == args[0]))).scalar_one_or_none()
            if not h: return await message.answer(f"❌ কোড `{house_code}` পাওয়া যায়নি।")
            cur = h.subscription_date or datetime.now()
            h.subscription_date = max(cur, datetime.now()) + timedelta(days=int(args[1]))
            await session.commit()

            await message.answer(
                f"✅ **সাবস্ক্রিপশন রিনিউ সফল!**\n\n"
                f"🏠 হাউজ: {h.name}\n"
                f"➕ যোগ করা হয়েছে: {days_to_add} দিন\n"
                f"📅 নতুন মেয়াদ: {h.subscription_date.strftime('%d-%m-%Y')}",
                parse_mode="Markdown"
            )

    except: await message.answer("ভুল ফরম্যাট! /renew CODE DAYS")


@router.message(F.text == "⚙️ সেটিংস", flags={"permission": "manage_settings"})
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

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer("প্রধান মেনু:", reply_markup=get_admin_main_menu())