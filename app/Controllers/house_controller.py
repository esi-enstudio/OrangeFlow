from sqlalchemy import select
from app.Views.keyboards.inline import get_house_list_keyboard
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.Models.house import House
from app.Services.db_service import async_session

router = Router()


# FSM ফরমের ধাপগুলো
class HouseCreateForm(StatesGroup):
    name = State()
    code = State()
    cluster = State()
    region = State()


@router.message(F.text == "📋 হাউজ লিস্ট দেখুন")
async def show_houses(message: Message):
    async with async_session() as session:
        # ডাটাবেজ থেকে সব হাউজ নিয়ে আসা
        result = await session.execute(select(House))
        houses = result.scalars().all()

        if not houses:
            return await message.answer("⚠️ বর্তমানে কোনো হাউজ নিবন্ধিত নেই।")

        response = "🏠 **নিবন্ধিত হাউজ তালিকা**\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n\n"

        for index, h in enumerate(houses, start=1):
            response += f"🏢 **হাউজ #{index}**\n"
            response += f"🔹 নাম: {h.name}\n"
            response += f"🔑 কোড: `{h.code}`\n"
            response += f"🌍 ক্লাস্টার: {h.cluster}\n"
            response += f"📍 রিজিয়ন: {h.region}\n"
            response += f"📧 ইমেইল: {h.email or 'N/A'}\n"
            response += f"🏠 ঠিকানা: {h.address or 'N/A'}\n"
            response += f"📞 কন্টাক্ট: {h.contact or 'N/A'}\n"
            response += f"📅 মেয়াদ শেষ: {h.subscription_date.strftime('%d-%m-%Y')}\n"
            response += "────────────────────\n"

        await message.answer(response, parse_mode="Markdown")
        return None


# নির্দিষ্ট হাউজে ক্লিক করলে তার বিস্তারিত তথ্য দেখানো
@router.callback_query(F.data.startswith("view_house_"))
async def view_house_details(callback_query):
    house_id = int(callback_query.data.split("_")[2])

    async with async_session() as session:
        house = await session.get(House, house_id)

        if house:
            details = (
                f"🏠 **হাউজের বিস্তারিত** 🏠\n\n"
                f"🔹 নাম: {house.name}\n"
                f"🔹 কোড: {house.code}\n"
                f"🔹 ক্লাস্টার: {house.cluster}\n"
                f"🔹 রিজিয়ন: {house.region}\n"
                f"🔹 ইমেইল: {house.email or 'N/A'}\n"
                f"🔹 কন্টাক্ট: {house.contact or 'N/A'}\n"
            )
            await callback_query.message.answer(details, parse_mode="Markdown")
        else:
            await callback_query.answer("হাউজটি খুঁজে পাওয়া যায়নি।")


@router.message(F.text == "➕ নতুন হাউজ তৈরি")
async def start_house_creation(message: Message, state: FSMContext):
    await message.answer("হাউজের নাম (House Name) লিখুন:")
    await state.set_state(HouseCreateForm.name)


@router.message(HouseCreateForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("হাউজ কোড (House Code) লিখুন: (উদা: MYMVAI01)")
    await state.set_state(HouseCreateForm.code)


@router.message(HouseCreateForm.code)
async def process_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text)
    await message.answer("ক্লাস্টার (Cluster) এর নাম লিখুন: (উদা: East)")
    await state.set_state(HouseCreateForm.cluster)


@router.message(HouseCreateForm.cluster)
async def process_cluster(message: Message, state: FSMContext):
    await state.update_data(cluster=message.text)
    await message.answer("রিজিয়ন (Region) এর নাম লিখুন:")
    await state.set_state(HouseCreateForm.region)


# ফাইনাল স্টেপ: ডাটাবেজে সেভ করা
@router.message(HouseCreateForm.region)
async def save_house(message: Message, state: FSMContext):
    user_data = await state.get_data()
    region = message.text

    # ডাটাবেজে সেভ করার লজিক
    async with async_session() as session:
        new_house = House(
            name=user_data['name'],
            code=user_data['code'],
            cluster=user_data['cluster'],
            region=region
        )
        session.add(new_house)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ সফলভাবে হাউজ তৈরি হয়েছে!\n\nনাম: {user_data['name']}\nকোড: {user_data['code']}")