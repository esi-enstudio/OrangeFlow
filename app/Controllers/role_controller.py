from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete
from app.Models.role import Role, Permission
from app.Services.db_service import async_session
from sqlalchemy.orm import selectinload
from config.settings import SUPER_ADMIN_ID

router = Router()


class RoleCreateForm(StatesGroup):
    name = State()
    perms = State()

class RoleUpdateForm(StatesGroup):
    role_id = State()
    new_name = State()
    perms = State()


class PermCreateForm(StatesGroup):
    name = State()


# --- ১. পারমিশন তৈরি ---
@router.message(F.text == "➕ নতুন পারমিশন তৈরি", flags={"permission": "manage_settings"})
async def start_perm_creation(message: Message, state: FSMContext):
    await state.clear()
    if int(message.from_user.id) == SUPER_ADMIN_ID:
        await message.answer("পারমিশনের নাম লিখুন (উদা: view_houses):")
        await state.set_state(PermCreateForm.name)


@router.message(PermCreateForm.name)
async def save_permission(message: Message, state: FSMContext):
    perm_name = message.text.lower().replace(" ", "_")
    async with async_session() as session:
        session.add(Permission(name=perm_name))
        await session.commit()
    await state.clear()
    await message.answer(f"✅ পারমিশন '{perm_name}' সফলভাবে তৈরি হয়েছে।")


# --- ২. রোল তৈরি ও পারমিশন সিলেকশন কিবোর্ড ---
@router.message(F.text == "➕ নতুন রোল তৈরি", flags={"permission": "manage_settings"})
async def start_role_creation(message: Message, state: FSMContext):
    # চেক করা হচ্ছে কোনো ফ্ল্যাগ আছে কি না
    data = await state.get_data()
    was_redirected = data.get("is_redirected_from_user", False)

    if int(message.from_user.id) == SUPER_ADMIN_ID:
        # স্টেট ক্লিয়ার না করে শুধু নতুন তথ্য যোগ করা
        await state.set_state(RoleCreateForm.name)
        await state.update_data(is_redirected_from_user=was_redirected)

        await message.answer("রোলের নাম লিখুন (উদা: Manager):")


@router.message(RoleCreateForm.name)
async def process_role_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text, selected_perms=[])  # শুরুতে খালি লিস্ট

    async with async_session() as session:
        result = await session.execute(select(Permission))
        all_permissions = result.scalars().all()

        if not all_permissions:
            return await message.answer("⚠️ আগে পারমিশন তৈরি করুন।")

        builder = InlineKeyboardBuilder()
        for p in all_permissions:
            builder.button(text=f"🔘 {p.name}", callback_data=f"toggle_p_{p.id}")
        builder.button(text="💾 সেভ করুন", callback_data="save_role_final")
        builder.adjust(2)

        await message.answer(f"রোল: {message.text}\nপারমিশন সিলেক্ট করুন:", reply_markup=builder.as_markup())
        await state.set_state(RoleCreateForm.perms)


# --- ৩. পারমিশন টগল (সিলেক্ট/আনসিলেক্ট) হ্যান্ডেলার ---
@router.callback_query(F.data.startswith("toggle_p_"))
async def toggle_permission(callback: CallbackQuery, state: FSMContext):
    perm_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("selected_perms", [])

    # টগল লজিক: থাকলে রিমুভ করো, না থাকলে অ্যাড করো
    if perm_id in selected:
        selected.remove(perm_id)
    else:
        selected.append(perm_id)

    await state.update_data(selected_perms=selected)

    # বাটনগুলো আপডেট করা (✅ চিহ্ন দেখানো)
    async with async_session() as session:
        res = await session.execute(select(Permission))
        all_perms = res.scalars().all()

        builder = InlineKeyboardBuilder()
        for p in all_perms:
            status = "✅" if p.id in selected else "🔘"
            builder.button(text=f"{status} {p.name}", callback_data=f"toggle_p_{p.id}")

        builder.button(text="💾 সেভ করুন", callback_data="save_role_final")
        builder.adjust(2)

        # মেসেজ এডিট করে নতুন কিবোর্ড পাঠানো
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()  # লোডিং আইকন বন্ধ করা


# --- ফাইনাল সেভ লজিক ---
@router.callback_query(F.data == "save_role_final")
async def save_role_final(callback: CallbackQuery, state: FSMContext):
    # ১. স্টেট থেকে সব ডাটা সংগ্রহ করা
    data = await state.get_data()
    role_name = data.get('name')
    perm_ids = data.get('selected_perms', [])
    
    # ২. চেক করা হচ্ছে এটি কি ইউজার ক্রিয়েশন থেকে রিডাইরেক্ট হয়ে এসেছে কি না
    is_redirected = data.get("is_redirected_from_user", False)

    async with async_session() as session:
        # ৩. নতুন রোল তৈরি ও পারমিশন যুক্ত করা
        new_role = Role(name=role_name)
        if perm_ids:
            res = await session.execute(select(Permission).where(Permission.id.in_(perm_ids)))
            new_role.permissions = res.scalars().all()

        session.add(new_role)
        await session.commit()

    # ৪. ডাটাবেজ সেভ শেষে স্টেট ক্লিয়ার করা
    await state.clear()

    # ৫. লজিক অনুযায়ী রেসপন্স পাঠানো
    if is_redirected:
        # যদি রিডাইরেক্ট হয়ে আসে, তবেই কেবল বাটনটি দেখাবে
        builder = InlineKeyboardBuilder()
        builder.button(text="👤 ইউজার তৈরিতে ফিরে যান", callback_data="go_to_user_create")
        
        await callback.message.answer(
            f"✅ রোল '{role_name}' সফলভাবে তৈরি হয়েছে।\nএখন আপনি ইউজার তৈরি করতে পারেন।",
            reply_markup=builder.as_markup()
        )
    else:
        # সরাসরি রোল তৈরি করলে সাধারণ সাকসেস মেসেজ
        await callback.message.answer(f"✅ রোল '{role_name}' সফলভাবে তৈরি হয়েছে।")

    await callback.answer()

# --- ১. রোল ও পারমিশন লিস্ট (আপডেটেড উইথ ইনলাইন বাটন) ---
@router.message(F.text == "📋 রোল ও পারমিশন লিস্ট", flags={"permission": "manage_settings"})
async def show_roles_and_permissions(message: Message):
    async with async_session() as session:
        roles = (await session.execute(select(Role).options(selectinload(Role.permissions)))).scalars().all()
        all_perms = (await session.execute(select(Permission))).scalars().all()

        if not roles and not all_perms:
            return await message.answer("⚠️ কোনো রোল বা পারমিশন নেই।")

        # রোলের জন্য ইনলাইন বাটন
        builder = InlineKeyboardBuilder()
        text = "🎭 **রোল ম্যানেজমেন্ট**\nনিচের রোলটিতে ক্লিক করে এডিট বা ডিলিট করুন:\n\n"
        
        for r in roles:
            p_count = len(r.permissions)
            builder.button(text=f"⚙️ {r.name} ({p_count})", callback_data=f"manage_role_{r.id}")
        
        builder.adjust(1)
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

        # পারমিশনের জন্য আলাদা লিস্ট (ডিলিট করার অপশনসহ)
        if all_perms:
            p_builder = InlineKeyboardBuilder()
            p_text = "\n🔑 **সিস্টেম পারমিশন তালিকা:**\n(ডিলিট করতে বাটনে চাপ দিন)"
            for p in all_perms:
                p_builder.button(text=f"❌ {p.name}", callback_data=f"del_perm_{p.id}")
            p_builder.adjust(2)
            await message.answer(p_text, reply_markup=p_builder.as_markup())

# --- ২. নির্দিষ্ট রোল ম্যানেজমেন্ট (Edit/Delete Menu) ---
@router.callback_query(F.data.startswith("manage_role_"))
async def manage_single_role(callback: CallbackQuery):
    role_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        role = await session.get(Role, role_id, options=[selectinload(Role.permissions)])
        perms = ", ".join([f"`{p.name}`" for p in role.permissions]) or "নেই"
        
        text = f"🎭 **রোল:** {role.name}\n🛠 **পারমিশন:** {perms}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✏️ নাম পরিবর্তন", callback_data=f"rename_role_{role_id}")
        builder.button(text="🔐 পারমিশন পরিবর্তন", callback_data=f"edit_role_perms_{role_id}")
        builder.button(text="🗑 রোল ডিলিট", callback_data=f"confirm_del_role_{role_id}")
        builder.button(text="🔙 লিস্টে ফিরুন", callback_data="refresh_role_list")
        builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- ৩. রোল রিনেম (Rename Logic) ---
@router.callback_query(F.data.startswith("rename_role_"))
async def start_rename_role(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[2])
    await state.update_data(edit_role_id=role_id)
    await callback.message.answer("রোলের নতুন নাম লিখে পাঠান:")
    await state.set_state(RoleUpdateForm.new_name)
    await callback.answer()

@router.message(RoleUpdateForm.new_name)
async def save_rename_role(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        role = await session.get(Role, data['edit_role_id'])
        old_name = role.name
        role.name = message.text
        await session.commit()
    await state.clear()
    await message.answer(f"✅ রোল '{old_name}' রিনেম হয়ে '{message.text}' হয়েছে।")

# --- ৪. বিদ্যমান রোলের পারমিশন আপডেট (Toggle Update) ---
@router.callback_query(F.data.startswith("edit_role_perms_"))
async def edit_role_perms_start(callback: CallbackQuery, state: FSMContext):
    role_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        role = await session.get(Role, role_id, options=[selectinload(Role.permissions)])
        current_perms = [p.id for p in role.permissions]
        all_perms = (await session.execute(select(Permission))).scalars().all()
        
        await state.update_data(edit_role_id=role_id, selected_perms=current_perms)
        
        builder = InlineKeyboardBuilder()
        for p in all_perms:
            status = "✅" if p.id in current_perms else "🔘"
            builder.button(text=f"{status} {p.name}", callback_data=f"upd_toggle_p_{p.id}")
        
        builder.button(text="💾 আপডেট সেভ করুন", callback_data="save_updated_role_perms")
        builder.adjust(2)
        await callback.message.edit_text(f"রোল: {role.name}\nপারমিশন আপডেট করুন:", reply_markup=builder.as_markup())
        await state.set_state(RoleUpdateForm.perms)

@router.callback_query(F.data.startswith("upd_toggle_p_"), RoleUpdateForm.perms)
async def toggle_edit_permission(callback: CallbackQuery, state: FSMContext):
    perm_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_perms", [])

    if perm_id in selected: selected.remove(perm_id)
    else: selected.append(perm_id)
    
    await state.update_data(selected_perms=selected)
    
    async with async_session() as session:
        all_perms = (await session.execute(select(Permission))).scalars().all()
        builder = InlineKeyboardBuilder()
        for p in all_perms:
            status = "✅" if p.id in selected else "🔘"
            builder.button(text=f"{status} {p.name}", callback_data=f"upd_toggle_p_{p.id}")
        builder.button(text="💾 আপডেট সেভ করুন", callback_data="save_updated_role_perms")
        builder.adjust(2)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

@router.callback_query(F.data == "save_updated_role_perms")
async def finalize_role_perm_update(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        role = await session.get(Role, data['edit_role_id'], options=[selectinload(Role.permissions)])
        new_perms = (await session.execute(select(Permission).where(Permission.id.in_(data['selected_perms'])))).scalars().all()
        role.permissions = new_perms
        await session.commit()
    await state.clear()
    await callback.message.answer(f"✅ রোলের পারমিশন সফলভাবে আপডেট হয়েছে।")
    await callback.answer()

# --- ৫. ডিলিট লজিক (Role & Permission) ---
@router.callback_query(F.data.startswith("confirm_del_role_"))
async def delete_role(callback: CallbackQuery):
    role_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if role:
            await session.delete(role)
            await session.commit()
            await callback.answer(f"🗑 রোল '{role.name}' ডিলিট করা হয়েছে।", show_alert=True)
    await show_roles_and_permissions(callback.message)

@router.callback_query(F.data.startswith("del_perm_"))
async def delete_permission(callback: CallbackQuery):
    perm_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        # ১. পিভট টেবিল (roles_permissions) থেকে ইম্পোর্ট করা
        from app.Models.role import role_permissions
        
        # ২. প্রথমে পিভট টেবিল থেকে এই পারমিশনের সব অ্যাসাইনমেন্ট বা লিংক ডিলিট করা
        await session.execute(
            delete(role_permissions).where(role_permissions.c.permission_id == perm_id)
        )
        
        # ৩. এখন মূল পারমিশন টেবিল থেকে পারমিশনটি ডিলিট করা
        perm = await session.get(Permission, perm_id)
        if perm:
            perm_name = perm.name
            await session.delete(perm)
            await session.commit()
            await callback.answer(f"🗑 পারমিশন '{perm_name}' সফলভাবে ডিলিট হয়েছে।", show_alert=True)
        else:
            await callback.answer("⚠️ পারমিশনটি পাওয়া যায়নি।", show_alert=True)

    # ৪. লিস্ট রিফ্রেশ করা
    await show_roles_and_permissions(callback.message)

@router.callback_query(F.data == "refresh_role_list")
async def refresh_roles(callback: CallbackQuery):
    await callback.message.delete()
    await show_roles_and_permissions(callback.message)




# @router.message(F.text == "📋 রোল ও পারমিশন লিস্ট", flags={"permission": "manage_settings"})
# async def show_roles_and_permissions(message: Message):
#     async with async_session() as session:
#         # ১. সব রোল এবং তাদের পারমিশন লোড করা
#         roles_result = await session.execute(
#             select(Role).options(selectinload(Role.permissions))
#         )
#         roles = roles_result.scalars().all()

#         # ২. সব আলাদা পারমিশন লোড করা (সিস্টেমে মোট কয়টি আছে দেখার জন্য)
#         perms_result = await session.execute(select(Permission))
#         all_permissions = perms_result.scalars().all()

#         if not roles and not all_permissions:
#             return await message.answer("⚠️ সিস্টেমে কোনো রোল বা পারমিশন তৈরি করা নেই।")

#         # ৩. মেসেজ ফরমেটিং
#         response = "🔐 **সিস্টেম এক্সেস কন্ট্রোল লিস্ট**\n"
#         response += "━━━━━━━━━━━━━━━━━━━━\n\n"

#         # রোল ও তাদের পারমিশন সেকশন
#         response += "🎭 **রোল ভিত্তিক পারমিশন:**\n"
#         if roles:
#             for r in roles:
#                 p_list = ", ".join([f"`{p.name}`" for p in r.permissions]) if r.permissions else "_কোনো পারমিশন নেই_"
#                 response += f"🔹 **{r.name}**\n┗ 🛠 {p_list}\n\n"
#         else:
#             response += "_কোনো রোল নেই_\n\n"

#         response += "────────────────────\n"
        
#         # সব পারমিশনের লিস্ট সেকশন
#         response += "🔑 **সিস্টেমের সকল পারমিশন:**\n"
#         if all_permissions:
#             p_names = ", ".join([f"`{p.name}`" for p in all_permissions])
#             response += f"⚙️ {p_names}\n"
#         else:
#             response += "_কোনো পারমিশন তৈরি করা নেই_"

#         await message.answer(response, parse_mode="Markdown")












# এই বাটনটি হ্যান্ডেল করার জন্য নতুন ফাংশন
@router.callback_query(F.data == "go_to_user_create")
async def go_back_to_user(callback: CallbackQuery, state: FSMContext):
    # সরাসরি ইউজার তৈরির প্রথম ধাপে নিয়ে যাবে
    from app.Controllers.admin_controller import UserCreateForm
    await callback.message.answer("ইউজারের টেলিগ্রাম আইডি (Telegram ID) লিখুন:")
    await state.set_state(UserCreateForm.telegram_id)
    await callback.answer()