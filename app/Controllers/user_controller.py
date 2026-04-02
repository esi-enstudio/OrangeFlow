import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.Models.user import User as DBUser # aiogram.types.User এর সাথে কনফ্লিক্ট এড়াতে
from app.Models.role import Role
from app.Models.house import House
from app.Services.db_service import async_session
from app.Views.keyboards.reply import get_user_mgmt_menu, get_settings_menu

router = Router()

# ==========================================
# 1. FSM STATES
# ==========================================

class UserCreateForm(StatesGroup):
    telegram_id = State()
    name = State()
    phone = State()
    role_ids = State()   # মাল্টি-রোল
    house_ids = State()  # মাল্টি-হাউজ

class UserUpdateForm(StatesGroup):
    user_id = State()
    field = State()
    new_value = State()

class UserHouseUpdateForm(StatesGroup):
    user_id = State()
    selected_house_ids = State()




# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

async def render_user_details(message: Message, user_id: int):
    """ইউজারের বিস্তারিত তথ্য দেখানোর কমন ফাংশন"""
    async with async_session() as session:
        result = await session.execute(
            select(DBUser)
            .where(DBUser.id == user_id)
            .options(selectinload(DBUser.roles), selectinload(DBUser.houses))
        )
        u = result.scalar_one_or_none()
        if not u:
            return await message.answer("❌ ইউজার পাওয়া যায়নি।")
            
        house_names = ", ".join([h.name for h in u.houses]) if u.houses else "হাউজ নেই"
        role_names = ", ".join([r.name for r in u.roles]) if u.roles else "রোল নেই"

        details = (
            f"👤 **ইউজার ডিটেইলস**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏠 হাউজ(সমূহ): **{house_names}**\n"
            f"🆔 আইডি: `{u.telegram_id}`\n"
            f"📛 নাম: {u.name}\n"
            f"📞 ফোন: {u.phone_number or 'দেওয়া নেই'}\n"
            f"🛠 রোল: {role_names}\n"
            f"────────────────────"
        )
        from app.Views.keyboards.inline import get_user_action_kb
        # যদি এটি কলব্যাক থেকে আসে তবে এডিট করবে, নাহলে নতুন মেসেজ দিবে
        if hasattr(message, 'edit_text'):
            await message.edit_text(details, reply_markup=get_user_action_kb(u.id), parse_mode="Markdown")
        else:
            await message.answer(details, reply_markup=get_user_action_kb(u.id), parse_mode="Markdown")

# ==========================================
# 3. USER MANAGEMENT UI
# ==========================================

@router.message(F.text == "👤 ইউজার ম্যানেজমেন্ট", flags={"permission": "view_users"})
async def user_mgmt_menu(message: Message):
    await message.answer("👤 ইউজার ম্যানেজমেন্ট অপশনসমূহ:", reply_markup=get_user_mgmt_menu())

@router.message(F.text == "📋 ইউজার লিস্ট দেখুন", flags={"permission": "view_users"})
async def show_user_list(message: Message):
    async with async_session() as session:
        result = await session.execute(select(DBUser).options(selectinload(DBUser.houses)))
        users = result.scalars().all()

        if not users: 
            return await message.answer("⚠️ কোনো ইউজার নেই।")
            
        builder = InlineKeyboardBuilder()
        for u in users:
            # লিস্টে প্রথম হাউজের নাম অথবা হাউজ সংখ্যা দেখাবে
            h_info = u.houses[0].name if u.houses else "হাউজ নেই"
            if len(u.houses) > 1: h_info += f" (+{len(u.houses)-1})"
            
            builder.button(text=f"👤 {u.name} ({h_info})", callback_data=f"manage_u_{u.id}")

        builder.adjust(1)
        await message.answer("👥 নিবন্ধিত ইউজার তালিকা:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "back_to_ulist")
async def back_to_user_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.delete()
    except: pass
    await show_user_list(callback.message)
    await callback.answer()



# ==========================================
# 4. USER CREATION FLOW (MULTI-HOUSE SUPPORT)
# ==========================================

@router.message(F.text == "➕ নতুন ইউজার তৈরি", flags={"permission": "create_user"})
async def start_user_creation(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        if not (await session.execute(select(Role))).scalars().first():
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
        builder = InlineKeyboardBuilder()
        for r in roles:
            builder.button(text=f"🔘 {r.name}", callback_data=f"cr_toggle_role_{r.id}")
        builder.button(text="✅ এগিয়ে যান", callback_data="cr_save_roles")
        builder.adjust(2)
        await message.answer("ইউজারের রোল সিলেক্ট করুন:", reply_markup=builder.as_markup())
        await state.set_state(UserCreateForm.role_ids)

@router.callback_query(F.data.startswith("cr_toggle_role_"), UserCreateForm.role_ids)
async def toggle_create_role(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_roles", [])
    if role_id in selected: selected.remove(role_id)
    else: selected.append(role_id)
    await state.update_data(selected_roles=selected)
    
    async with async_session() as session:
        roles = (await session.execute(select(Role))).scalars().all()
        builder = InlineKeyboardBuilder()
        for r in roles:
            status = "✅" if r.id in selected else "🔘"
            builder.button(text=f"{status} {r.name}", callback_data=f"cr_toggle_role_{r.id}")
        builder.button(text="✅ এগিয়ে যান", callback_data="cr_save_roles")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

@router.callback_query(F.data == "cr_save_roles", UserCreateForm.role_ids)
async def start_house_selection_creation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_roles"):
        return await callback.answer("⚠️ অন্তত একটি রোল সিলেক্ট করুন!", show_alert=True)
    
    await state.update_data(selected_house_ids=[])
    async with async_session() as session:
        houses = (await session.execute(select(House))).scalars().all()
        builder = InlineKeyboardBuilder()
        for h in houses:
            builder.button(text=f"🔘 {h.name}", callback_data=f"cr_toggle_house_{h.id}")
        builder.button(text="💾 ইউজার সেভ করুন", callback_data="cr_save_user_final")
        builder.adjust(2)
        await callback.message.edit_text("ইউজারের জন্য হাউজ(সমূহ) সিলেক্ট করুন:", reply_markup=builder.as_markup())
        await state.set_state(UserCreateForm.house_ids)
        await callback.answer()

@router.callback_query(F.data.startswith("cr_toggle_house_"), UserCreateForm.house_ids)
async def toggle_create_house(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_house_ids", [])
    if house_id in selected: selected.remove(house_id)
    else: selected.append(house_id)
    await state.update_data(selected_house_ids=selected)
    
    async with async_session() as session:
        houses = (await session.execute(select(House))).scalars().all()
        builder = InlineKeyboardBuilder()
        for h in houses:
            status = "✅" if h.id in selected else "🔘"
            builder.button(text=f"{status} {h.name}", callback_data=f"cr_toggle_house_{h.id}")
        builder.button(text="💾 ইউজার সেভ করুন", callback_data="cr_save_user_final")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

@router.callback_query(F.data == "cr_save_user_final", UserCreateForm.house_ids)
async def save_user_final(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_house_ids"):
        return await callback.answer("⚠️ অন্তত একটি হাউজ সিলেক্ট করুন!", show_alert=True)

    async with async_session() as session:
        # রোল এবং হাউজ অবজেক্ট লোড করা
        roles = (await session.execute(select(Role).where(Role.id.in_(data['selected_roles'])))).scalars().all()
        houses = (await session.execute(select(House).where(House.id.in_(data['selected_house_ids'])))).scalars().all()
        
        new_user = DBUser(
            telegram_id=data['telegram_id'],
            name=data['name'],
            phone_number=data['phone'],
            roles=roles,
            houses=houses
        )
        session.add(new_user)
        await session.commit()
        
    await state.clear()
    await callback.message.answer(f"✅ ইউজার '{data['name']}' সফলভাবে তৈরি হয়েছে।")
    await callback.answer()




# class UserCreateForm(StatesGroup):
#     telegram_id = State()
#     name = State()
#     phone = State()
#     role_id = State() # মাল্টি-রোল সিলেকশনের জন্য ব্যবহৃত

# class UserUpdateForm(StatesGroup):
#     user_id = State()
#     field = State()
#     new_value = State()

# class UserHouseUpdateForm(StatesGroup):
#     user_id = State()
#     selected_house_ids = State()

# async def render_user_details(message: Message, user_id: int):
#     """ইউজারের বিস্তারিত তথ্য দেখানোর কমন ফাংশন (এরর এড়াতে এটি জরুরি)"""
#     async with async_session() as session:
#         result = await session.execute(
#             select(User)
#             .where(User.id == user_id)
#             .options(selectinload(User.roles), selectinload(User.house))
#         )
#         u = result.scalar_one_or_none()
#         if not u:
#             return await message.answer("❌ ইউজার পাওয়া যায়নি।")
            
#         house_name = u.house.name if u.house else "N/A"
#         role_names = ", ".join([r.name for r in u.roles]) if u.roles else "রোল নেই"

#         details = (
#             f"👤 **ইউজার ডিটেইলস**\n"
#             f"━━━━━━━━━━━━━━━━━━━━\n"
#             f"🏠 হাউজ: **{house_name}**\n"
#             f"📛 নাম: {u.name}\n"
#             f"📞 ফোন: {u.phone_number or 'দেওয়া নেই'}\n"
#             f"🛠 রোল: {role_names}\n"
#             f"────────────────────"
#         )
#         from app.Views.keyboards.inline import get_user_action_kb
#         await message.edit_text(details, reply_markup=get_user_action_kb(u.id), parse_mode="Markdown")
        
# @router.message(F.text == "👤 ইউজার ম্যানেজমেন্ট", flags={"permission": "view_users"})
# async def user_mgmt_menu(message: Message):
#     await message.answer(
#         "👤 ইউজার ম্যানেজমেন্ট অপশনসমূহ:", 
#         reply_markup=get_user_mgmt_menu()
    )

# --- ইউজার লিস্ট দেখুন ---
# @router.message(F.text == "📋 ইউজার লিস্ট দেখুন", flags={"permission": "view_users"})
# async def show_user_list(message: Message):
#     async with async_session() as session:

#         result = await session.execute(
#             select(User).options(selectinload(User.house))
#         )
#         users = result.scalars().all()

#         if not users: return await message.answer("⚠️ কোনো ইউজার নেই।")
#         builder = InlineKeyboardBuilder()
#         for u in users:
#             house_name = u.house.name if u.house else "হাউজ নেই"
#             builder.button(
#                 text=f"👤 {u.name} ({house_name})", 
#                 callback_data=f"manage_u_{u.id}"
#             )

#         builder.adjust(1)
#         await message.answer("👥 নিবন্ধিত ইউজার তালিকা:", reply_markup=builder.as_markup())

# @router.callback_query(F.data == "back_to_ulist")
# async def back_to_user_list(callback: CallbackQuery, state: FSMContext = None): # ডিফল্ট None
#     # যদি state অবজেক্ট থাকে তবেই ক্লিয়ার করবে
#     if state:
#         await state.clear()
    
#     try: 
#         await callback.message.delete()
#     except: 
#         pass
        
#     # তালিকা পুনরায় দেখানোর জন্য আপনার মেইন ফাংশনটি কল করা
#     await show_user_list(callback.message)
#     await callback.answer()

# --- নতুন ইউজার তৈরি শুরু ---
# @router.message(F.text == "➕ নতুন ইউজার তৈরি", flags={"permission": "create_user"})
# async def start_user_creation(message: Message, state: FSMContext):
#     await state.clear()
#     async with async_session() as session:
#         res = await session.execute(select(Role))
#         if not res.scalars().all():
#             return await message.answer("⚠️ আগে রোল তৈরি করুন!", reply_markup=get_settings_menu())
#     await message.answer("ইউজারের টেলিগ্রাম আইডি (Telegram ID) লিখুন:")
#     await state.set_state(UserCreateForm.telegram_id)

# @router.message(UserCreateForm.telegram_id)
# async def process_user_tid(message: Message, state: FSMContext):
#     if not message.text.isdigit():
#         return await message.answer("ভুল আইডি! শুধুমাত্র সংখ্যা লিখুন।")
#     await state.update_data(telegram_id=int(message.text))
#     await message.answer("ইউজারের নাম লিখুন:")
#     await state.set_state(UserCreateForm.name)

# @router.message(UserCreateForm.name)
# async def process_user_name(message: Message, state: FSMContext):
#     await state.update_data(name=message.text)
#     await message.answer("ইউজারের ফোন নাম্বার লিখুন:")
#     await state.set_state(UserCreateForm.phone)

# @router.message(UserCreateForm.phone)
# async def process_user_phone(message: Message, state: FSMContext):
#     await state.update_data(phone=message.text, selected_roles=[])
#     async with async_session() as session:
#         roles = (await session.execute(select(Role))).scalars().all()
#         if not roles:
#             await state.update_data(is_redirected_from_user=True)
#             return await message.answer("⚠️ রোল নেই! আগে রোল তৈরি করুন।", reply_markup=get_settings_menu())

#         builder = InlineKeyboardBuilder()
#         for r in roles:
#             builder.button(text=f"🔘 {r.name}", callback_data=f"toggle_user_role_{r.id}")
#         builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
#         builder.adjust(2)
#         await message.answer("ইউজারের রোল সিলেক্ট করুন:", reply_markup=builder.as_markup())
#         await state.set_state(UserCreateForm.role_id)

# @router.callback_query(F.data.startswith("toggle_user_role_"))
# async def toggle_user_role(callback: CallbackQuery, state: FSMContext):
#     role_id = int(callback.data.split("_")[3])
#     data = await state.get_data()
#     selected = data.get("selected_roles", [])
#     if role_id in selected: selected.remove(role_id)
#     else: selected.append(role_id)
#     await state.update_data(selected_roles=selected)

#     async with async_session() as session:
#         all_roles = (await session.execute(select(Role))).scalars().all()
#         builder = InlineKeyboardBuilder()
#         for r in all_roles:
#             status = "✅" if r.id in selected else "🔘"
#             builder.button(text=f"{status} {r.name}", callback_data=f"toggle_user_role_{r.id}")
#         builder.button(text="✅ সেভ ও এগিয়ে যান", callback_data="save_user_roles")
#         builder.adjust(2)
#         await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
#         await callback.answer()

# @router.callback_query(F.data == "save_user_roles")
# async def save_user_roles_step(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     if not data.get("selected_roles"):
#         return await callback.answer("⚠️ অন্তত একটি রোল সিলেক্ট করুন!", show_alert=True)
    
#     async with async_session() as session:
#         # ডাটাবেজ থেকে সব হাউজ নিয়ে আসা
#         result = await session.execute(select(House))
#         houses = result.scalars().all()

#         if not houses:
#             await state.clear()
#             return await callback.message.answer("⚠️ কোনো হাউজ তৈরি করা নেই! আগে হাউজ তৈরি করুন।")

#         builder = InlineKeyboardBuilder()
#         for h in houses:
#             # বাটনের টেক্সটে হাউজের নাম এবং ক্লিক করলে আইডি যাবে
#             builder.button(text=f"🏢 {h.name}", callback_data=f"sel_h_{h.id}")
        
#         # এক লাইনে ২টি করে বাটন (adjust 2)
#         builder.adjust(2)

#         await callback.message.edit_text(
#             "ইউজারের জন্য একটি হাউজ সিলেক্ট করুন:", 
#             reply_markup=builder.as_markup()
#         )
#         await state.set_state(UserCreateForm.house_id)
#         await callback.answer()


# @router.callback_query(F.data.startswith("sel_h_"), UserCreateForm.house_id)
# async def save_user_final(callback: CallbackQuery, state: FSMContext):
#     house_id = int(callback.data.split("_")[2])
#     data = await state.get_data()

#     async with async_session() as session:
#         # সিলেক্ট করা হাউজ এবং রোলগুলো নিয়ে আসা
#         house = await session.get(House, house_id)
#         r_res = await session.execute(select(Role).where(Role.id.in_(data['selected_roles'])))
        
#         # নতুন ইউজার তৈরি ও সেভ করা
#         new_user = User(
#             telegram_id=data['telegram_id'],
#             name=data['name'],
#             phone_number=data['phone'],
#             house_id=house_id, # ডাটাবেজে হাউজ আইডি সেভ হচ্ছে
#             roles=r_res.scalars().all()
#         )
#         session.add(new_user)
#         await session.commit()
        
#     await state.clear()
#     await callback.message.answer(
#         f"✅ ইউজার সফলভাবে তৈরি হয়েছে!\n"
#         f"👤 নাম: {data['name']}\n"
#         f"🏠 হাউজ: {house.name}"
#     )
#     await callback.answer()

# --- ইউজার অ্যাকশন (Edit/Delete) হ্যান্ডেলার্স ---
@router.callback_query(F.data.startswith("manage_u_"), flags={"permission": "view_users"})
async def view_user_actions(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    await render_user_details(callback.message, user_id)
    await callback.answer()

@router.callback_query(F.data.startswith("conf_del_u_"), flags={"permission": "delete_user"})
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

@router.callback_query(F.data == "save_user_roles")
async def show_house_selection(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        houses = (await session.execute(select(House))).scalars().all()
        if not houses: return await callback.answer("⚠️ আগে হাউজ তৈরি করুন।")

        builder = InlineKeyboardBuilder()
        await state.update_data(selected_house_ids=[]) # শুরুতে খালি
        
        for h in houses:
            builder.button(text=f"🔘 {h.name}", callback_data=f"toggle_user_h_{h.id}")
        
        builder.button(text="✅ সেভ ও সম্পন্ন করুন", callback_data="save_user_houses_final")
        builder.adjust(2)
        await callback.message.edit_text("ইউজারের জন্য হাউজ(সমূহ) সিলেক্ট করুন:", reply_markup=builder.as_markup())
        await state.set_state(UserCreateForm.selected_house_ids)


# --- ১. হাউজ এডিট শুরু ---
@router.callback_query(F.data.startswith("edit_user_houses_"), flags={"permission": "edit_user"})
async def edit_user_houses_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[3])
    
    async with async_session() as session:
        # ইউজার এবং তার বর্তমান হাউজগুলো লোড করা
        u = (await session.execute(
            select(User).options(selectinload(User.houses)).where(User.id == user_id)
        )).scalar_one_or_none()
        
        # সিস্টেমের সব হাউজ লোড করা
        all_h = (await session.execute(select(House))).scalars().all()
        
        current_house_ids = [h.id for h in u.houses]
        await state.update_data(editing_uid=user_id, selected_h_ids=current_house_ids)
        
        builder = InlineKeyboardBuilder()
        for h in all_h:
            status = "✅" if h.id in current_house_ids else "🔘"
            builder.button(text=f"{status} {h.name}", callback_data=f"toggle_u_h_edit_{h.id}")
        
        builder.button(text="💾 আপডেট সেভ করুন", callback_data="save_u_houses_edit")
        builder.button(text="🔙 ফিরে যান", callback_data=f"manage_u_{user_id}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"👤 **ইউজার:** {u.name}\nহাউজ(সমূহ) টিক দিন বা তুলে দিন:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        await state.set_state(UserHouseUpdateForm.selected_house_ids)

# --- ২. হাউজ টগল হ্যান্ডেলার (এডিট মোড) ---
@router.callback_query(F.data.startswith("toggle_u_h_edit_"), UserHouseUpdateForm.selected_house_ids)
async def toggle_edit_user_house(callback: CallbackQuery, state: FSMContext):
    house_id = int(callback.data.split("_")[4])
    data = await state.get_data()
    selected = data['selected_h_ids']

    if house_id in selected: selected.remove(house_id)
    else: selected.append(house_id)
    
    await state.update_data(selected_h_ids=selected)
    
    # বাটন রি-রেন্ডার করা
    async with async_session() as session:
        all_h = (await session.execute(select(House))).scalars().all()
        builder = InlineKeyboardBuilder()
        for h in all_h:
            status = "✅" if h.id in selected else "🔘"
            builder.button(text=f"{status} {h.name}", callback_data=f"toggle_u_h_edit_{h.id}")
        
        builder.button(text="💾 আপডেট সেভ করুন", callback_data="save_u_houses_edit")
        builder.button(text="🔙 ফিরে যান", callback_data=f"manage_u_{data['editing_uid']}")
        builder.adjust(2)
        
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

# --- ৩. ফাইনাল সেভ ---
@router.callback_query(F.data == "save_u_houses_edit")
async def save_user_houses_final(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data['editing_uid']
    house_ids = data['selected_h_ids']

    async with async_session() as session:
        # ইউজার লোড করা
        u = await session.get(User, user_id, options=[selectinload(User.houses)])
        # সিলেক্ট করা নতুন হাউজ অবজেক্টগুলো নিয়ে আসা
        new_houses = (await session.execute(
            select(House).where(House.id.in_(house_ids))
        )).scalars().all()
        
        # রিলেশনশিপ আপডেট (SQLAlchemy এটি অটো হ্যান্ডেল করবে)
        u.houses = new_houses
        await session.commit()
    
    await state.clear()
    await callback.answer("✅ হাউজ তালিকা সফলভাবে আপডেট হয়েছে।", show_alert=True)
    # ইউজারের ডিটেইলস পেজে ফেরত যাওয়া
    from app.Controllers.user_controller import render_user_details
    await render_user_details(callback.message, user_id)

@router.message(F.text == "🔙 প্রধান মেনু")
async def back_to_main(message: Message, state: FSMContext, permissions: list):
    """প্রধান মেনুতে ফিরে যাওয়া (পারমিশন অনুযায়ী বাটনসহ)"""
    await state.clear()
    
    from app.Views.keyboards.reply import get_admin_main_menu
    
    await message.answer(
        "আপনি প্রধান মেনুতে ফিরে এসেছেন।", 
        reply_markup=get_admin_main_menu(permissions)
    )