from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from app.Models.role import Role, Permission
from app.Services.db_service import async_session
from config.settings import SUPER_ADMIN_ID

router = Router()


class RoleCreateForm(StatesGroup):
    name = State()
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
        from aiogram.utils.keyboard import InlineKeyboardBuilder
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


# এই বাটনটি হ্যান্ডেল করার জন্য নতুন ফাংশন
@router.callback_query(F.data == "go_to_user_create")
async def go_back_to_user(callback: CallbackQuery, state: FSMContext):
    # সরাসরি ইউজার তৈরির প্রথম ধাপে নিয়ে যাবে
    from app.Controllers.admin_controller import UserCreateForm
    await callback.message.answer("ইউজারের টেলিগ্রাম আইডি (Telegram ID) লিখুন:")
    await state.set_state(UserCreateForm.telegram_id)
    await callback.answer()