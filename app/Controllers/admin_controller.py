import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.house import House
from app.Models.user import User
from app.Models.role import Role
from app.Services.db_service import async_session
from app.Views.keyboards.reply import get_admin_main_menu, get_house_mgmt_menu, get_settings_menu, get_user_mgmt_menu
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

class UserCreateForm(StatesGroup):
    telegram_id = State()
    name = State()
    phone = State()
    house_code = State()
    role_id = State() # মাল্টি-রোল সিলেকশনের জন্য ব্যবহৃত

class UserUpdateForm(StatesGroup):
    user_id = State()
    field = State()
    new_value = State()

class RoleCreateForm(StatesGroup):
    name = State()
    perms = State()


# ==========================================
# 2. HELPER FUNCTIONS (অভ্যন্তরীণ কাজের জন্য)
# ==========================================

async def render_user_details(message: Message, user_id: int):
    """ইউজারের বিস্তারিত তথ্য দেখানোর কমন ফাংশন (এরর এড়াতে এটি জরুরি)"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        u = result.scalar_one_or_none()
        if not u:
            return await message.answer("❌ ইউজার পাওয়া যায়নি।")
            
        role_names = ", ".join([r.name for r in u.roles]) if u.roles else "রোল নেই"
        details = (
            f"👤 **ইউজার ডিটেইলস**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 আইডি: `{u.telegram_id}`\n"
            f"📛 নাম: {u.name}\n"
            f"📞 ফোন: {u.phone_number or 'দেওয়া নেই'}\n"
            f"🛠 রোল: {role_names}\n"
            f"────────────────────"
        )
        from app.Views.keyboards.inline import get_user_action_kb
        await message.edit_text(details, reply_markup=get_user_action_kb(u.id), parse_mode="Markdown")


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

@router.message(F.text == "🏠 হাউজ ম্যানেজমেন্ট")
async def house_mgmt_menu(message: Message):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer("🏢 হাউজ ম্যানেজমেন্ট অপশন:", reply_markup=get_house_mgmt_menu())

@router.message(F.text == "👤 ইউজার ম্যানেজমেন্ট")
async def user_mgmt_menu(message: Message):
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
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

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) == int(SUPER_ADMIN_ID):
        await message.answer("প্রধান মেনু:", reply_markup=get_admin_main_menu())


# ==========================================
# 4. USER CREATION FLOW (ইউজার তৈরির ধাপসমূহ)
# ==========================================

@router.message(F.text == "➕ নতুন ইউজার তৈরি")
async def start_user_creation(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) != SUPER_ADMIN_ID: return

    async with async_session() as session:
        res = await session.execute(select(Role))
        if not res.scalars().all():
            return await message.answer("⚠️ আগে রোল তৈরি করুন!", reply_markup=get_settings_menu())

    await message.answer("ইউজারের টেলিগ্রাম আইডি (Telegram ID) লিখুন:")
    await state.set_state(UserCreateForm.telegram_id)

@router.message(UserCreateForm.telegram_id)
async def process_user_tid(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ভুল আইডি! শুধুমাত্র সংখ্যা লিখুন।")
    await state.update_data(telegram_id=int(message.text))
    await message.answer("ইউজারের নাম লিখুন:")
    await state.set_state(UserCreateForm.name)

@router.message(UserCreateForm.name)
async def process_user_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("ইউজারের ফোন নাম্বার লিখুন:")
    await state.set_state(UserCreateForm.phone)

@router.message(UserCreateForm.phone)
async def process_user_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text, selected_roles=[])
    async with async_session() as session:
        roles = (await session.execute(select(Role))).scalars().all()
        if not roles:
            await state.update_data(is_redirected_from_user=True)
            return await message.answer("⚠️ রোল নেই! আগে রোল তৈরি করুন।", reply_markup=get_settings_menu())

        builder = InlineKeyboardBuilder()
        for r in roles:
            builder.button(text=f"🔘 {r.name}", callback_data=f"toggle_user_role_{r.id}")
        builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
        builder.adjust(2)
        await message.answer("ইউজারের রোল সিলেক্ট করুন:", reply_markup=builder.as_markup())
        await state.set_state(UserCreateForm.role_id)

@router.callback_query(F.data.startswith("toggle_user_role_"))
async def toggle_user_role(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_roles", [])
    if role_id in selected: selected.remove(role_id)
    else: selected.append(role_id)
    await state.update_data(selected_roles=selected)

    async with async_session() as session:
        all_roles = (await session.execute(select(Role))).scalars().all()
        builder = InlineKeyboardBuilder()
        for r in all_roles:
            status = "✅" if r.id in selected else "🔘"
            builder.button(text=f"{status} {r.name}", callback_data=f"toggle_user_role_{r.id}")
        builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

@router.callback_query(F.data == "save_user_roles")
async def save_user_roles_step(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_roles"):
        return await callback.answer("⚠️ অন্তত একটি রোল সিলেক্ট করুন!", show_alert=True)
    await callback.message.answer("হাউজ কোড (House Code) লিখুন:")
    await state.set_state(UserCreateForm.house_code)
    await callback.answer()

@router.message(UserCreateForm.house_code)
async def save_user_final(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        h_res = await session.execute(select(House).where(House.code == message.text))
        house = h_res.scalar_one_or_none()
        if not house: return await message.answer("❌ ভুল হাউজ কোড!")

        r_res = await session.execute(select(Role).where(Role.id.in_(data['selected_roles'])))
        new_user = User(
            telegram_id=data['telegram_id'],
            name=data['name'],
            phone_number=data['phone'],
            roles=r_res.scalars().all()
        )
        session.add(new_user)
        await session.commit()
        
    await state.clear()
    await message.answer(f"✅ ইউজার সফলভাবে তৈরি হয়েছে!\n👤 নাম: {data['name']}\n🏠 হাউজ: {house.name}")


# ==========================================
# 5. USER MANAGEMENT (লিস্ট, আপডেট ও ডিলিট)
# ==========================================

@router.message(F.text == "📋 ইউজার লিস্ট দেখুন")
async def show_user_list(message: Message):
    # message.chat.id ব্যবহার করলে এটি সরাসরি এডমিনের চ্যাট আইডি চেক করবে 
    # যা মেসেজ বা বাটন—উভয় ক্ষেত্রেই কাজ করবে।
    if int(message.chat.id) != SUPER_ADMIN_ID: 
        return
    
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
        if not users: return await message.answer("⚠️ কোনো ইউজার নেই।")
        builder = InlineKeyboardBuilder()
        for u in users:
            builder.button(text=f"👤 {u.name} ({u.telegram_id})", callback_data=f"manage_u_{u.id}")
        builder.adjust(1)
        await message.answer("👥 নিবন্ধিত ইউজার তালিকা:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("manage_u_"))
async def view_user_actions(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    await render_user_details(callback.message, user_id)
    await callback.answer()

@router.callback_query(F.data == "back_to_ulist")
async def back_to_user_list(callback: CallbackQuery, state: FSMContext = None): # ডিফল্ট None
    # যদি state অবজেক্ট থাকে তবেই ক্লিয়ার করবে
    if state:
        await state.clear()
    
    try: 
        await callback.message.delete()
    except: 
        pass
        
    # তালিকা পুনরায় দেখানোর জন্য আপনার মেইন ফাংশনটি কল করা
    await show_user_list(callback.message)
    await callback.answer()

# --- ডিলিট লজিক ---
@router.callback_query(F.data.startswith("conf_del_u_"))
async def confirm_delete_user(callback: CallbackQuery):
    user_id = callback.data.split("_")[3]
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ হ্যাঁ, ডিলিট", callback_data=f"final_del_u_{user_id}")
    builder.button(text="❌ না, বাতিল", callback_data=f"manage_u_{user_id}")
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে এই ইউজারকে ডিলিট করতে চান?", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("final_del_u_"))
async def final_delete_user(callback: CallbackQuery, state: FSMContext): # state যোগ করা হয়েছে
    user_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        u = await session.get(User, user_id)
        if u:
            await session.delete(u)
            await session.commit()
            await callback.answer(f"✅ ইউজার '{u.name}' সফলভাবে ডিলিট হয়েছে।", show_alert=True)
    
    # এখানে 'None' এর পরিবর্তে 'state' পাস করতে হবে
    await back_to_user_list(callback, state)

# --- আপডেট লজিক ---
@router.callback_query(F.data.startswith("edit_uname_") | F.data.startswith("edit_uphone_"))
async def start_user_edit(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    # ফিল্টারটি কিবোর্ডের ID এর সাথে ম্যাচ করা হয়েছে
    field = "name" if "uname" in parts[1] else "phone"
    user_id = int(parts[2])
    
    await state.update_data(edit_uid=user_id, edit_field=field)
    label = "নাম" if field == "name" else "ফোন নাম্বার"
    await callback.message.answer(f"ইউজারের নতুন **{label}** লিখে পাঠান:")
    await state.set_state(UserUpdateForm.new_value)
    await callback.answer()

@router.message(UserUpdateForm.new_value)
async def save_user_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        u = await session.get(User, data['edit_uid'])
        if data['edit_field'] == "name": u.name = message.text
        else: u.phone_number = message.text
        await session.commit()
    await state.clear()
    await message.answer("✅ সফলভাবে আপডেট হয়েছে।")

# --- রোল আপডেট লজিক ---
@router.callback_query(F.data.startswith("edit_user_roles_"))
async def edit_user_roles_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        u = (await session.execute(select(User).where(User.id==user_id).options(selectinload(User.roles)))).scalar_one()
        all_r = (await session.execute(select(Role))).scalars().all()
        curr_ids = [r.id for r in u.roles]
        await state.update_data(editing_uid=user_id, selected_role_ids=curr_ids)
        builder = InlineKeyboardBuilder()
        for r in all_r:
            status = "✅" if r.id in curr_ids else "🔘"
            builder.button(text=f"{status} {r.name}", callback_data=f"toggle_u_edit_role_{r.id}")
        builder.button(text="💾 সেভ", callback_data="save_u_roles_edit")
        builder.button(text="🔙", callback_data=f"manage_u_{user_id}")
        builder.adjust(2)
        await callback.message.edit_text("রোল পরিবর্তন করুন:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("toggle_u_edit_role_"))
async def toggle_edit_role(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[4])
    data = await state.get_data()
    selected = data['selected_role_ids']
    if role_id in selected: selected.remove(role_id)
    else: selected.append(role_id)
    await state.update_data(selected_role_ids=selected)
    async with async_session() as session:
        all_r = (await session.execute(select(Role))).scalars().all()
        builder = InlineKeyboardBuilder()
        for r in all_r:
            status = "✅" if r.id in selected else "🔘"
            builder.button(text=f"{status} {r.name}", callback_data=f"toggle_u_edit_role_{r.id}")
        builder.button(text="💾 সেভ", callback_data="save_u_roles_edit")
        builder.button(text="🔙", callback_data=f"manage_u_{data['editing_uid']}")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

@router.callback_query(F.data == "save_u_roles_edit")
async def save_user_roles_final(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        u = await session.get(User, data['editing_uid'], options=[selectinload(User.roles)])
        r_res = await session.execute(select(Role).where(Role.id.in_(data['selected_role_ids'])))
        u.roles = r_res.scalars().all()
        await session.commit()
    await state.clear()
    await render_user_details(callback.message, data['editing_uid'])
    await callback.answer("✅ রোল আপডেট হয়েছে", show_alert=True)


# ==========================================
# 6. HOUSE MANAGEMENT (হাউজ ও সাবস্ক্রিপশন)
# ==========================================

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




# --- সাবস্ক্রিপশন রিনিউ কমান্ড ---
@router.message(Command("renew"))
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