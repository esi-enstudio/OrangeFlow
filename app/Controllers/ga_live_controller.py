import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.Models.user import User
from app.Models.house import House
from app.Models.live_activation import LiveActivation
from app.Services.db_service import async_session

# লগিং কনফিগারেশন
logger = logging.getLogger(__name__)

router = Router()

# ==========================================
# ১. রিপোর্টস মেইন মেনু (Reply Keyboard Handler)
# ==========================================

@router.message(F.text == "📊 রিপোর্টস", flags={"permission": "report_access"})
async def show_reports_menu(message: Message):
    """ইউজারকে রিপোর্টের তালিকা ইনলাইন বাটন হিসেবে দেখাবে"""
    builder = InlineKeyboardBuilder()
    
    # জিএ লাইভ রিপোর্টের জন্য বাটন (পারমিশন অনুযায়ী)
    builder.button(text="📡 জিএ লাইভ", callback_data="ga_live_main")
    
    # ভবিষ্যতে আরও রিপোর্ট যোগ করার জন্য এখানে বাটন বাড়ানো যাবে
    # builder.button(text="📈 সেলস রিপোর্ট", callback_data="sales_report")
    
    builder.adjust(1)
    
    await message.answer(
        "📊 **রিপোর্ট মডিউল**\nনিচের তালিকা থেকে কাঙ্খিত রিপোর্টটি নির্বাচন করুন:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ==========================================
# ২. জিএ লাইভ রিকোয়েস্ট হ্যান্ডেলার
# ==========================================

@router.callback_query(F.data == "ga_live_main", flags={"permission": "view_ga_live"})
async def handle_ga_live_request(callback: CallbackQuery):
    """চেক করবে ইউজারের কয়টি হাউজ আছে"""
    async with async_session() as session:
        # ইউজারের সাথে যুক্ত হাউজগুলো লোড করা
        result = await session.execute(
            select(User).options(selectinload(User.houses)).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.houses:
            return await callback.message.answer("❌ আপনার প্রোফাইলে কোনো হাউজ যুক্ত নেই।")

        # ১টি হাউজ থাকলে সরাসরি সামারি দেখাবে
        if len(user.houses) == 1:
            house = user.houses[0]
            await send_ga_summary(callback.message, house)
            await callback.answer()
            return

        # একাধিক হাউজ থাকলে সিলেকশন বাটন দেখাবে
        builder = InlineKeyboardBuilder()
        for h in user.houses:
            builder.button(text=f"🏢 {h.name}", callback_data=f"ga_hsel_{h.id}")
        builder.adjust(2)

        await callback.message.edit_text(
            "আপনার একাধিক হাউজ রয়েছে। কোন হাউজের **জিএ লাইভ** দেখতে চান?",
            reply_markup=builder.as_markup()
        )
    await callback.answer()


# ==========================================
# ৩. হাউজ সিলেকশন হ্যান্ডেলার
# ==========================================

@router.callback_query(F.data.startswith("ga_hsel_"), flags={"permission": "view_ga_live"})
async def process_house_selection_ga(callback: CallbackQuery):
    house_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        house = await session.get(House, house_id)
        if not house:
            return await callback.answer("❌ হাউজ পাওয়া যায়নি।", show_alert=True)
        
        await send_ga_summary(callback.message, house)
    
    await callback.answer()


# ==========================================
# ৪. সামারি জেনারেশন ফাংশন (Core Logic)
# ==========================================

async def send_ga_summary(message: Message, house: House):
    """ডাটাবেজ থেকে ডাটা নিয়ে সুন্দর ফরম্যাটে রিপোর্ট পাঠাবে"""
    async with async_session() as session:
        # ওই হাউজের আজকের মোট এক্টিভেশন সংখ্যা বের করা
        count = await session.scalar(
            select(func.count(LiveActivation.id)).where(LiveActivation.house_id == house.id)
        )

        # কিছু বাড়তি তথ্য (যেমন: শেষ ৩টি এক্টিভেশনের সময়) - ঐচ্ছিক
        last_act_res = await session.execute(
            select(LiveActivation.activation_time)
            .where(LiveActivation.house_id == house.id)
            .order_by(LiveActivation.id.desc())
            .limit(1)
        )
        last_time = last_act_res.scalar_one_or_none() or "ডাটা নেই"

        # রিপোর্ট টেক্সট তৈরি
        report_text = (
            f"📡 **জিএ লাইভ রিপোর্ট**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 হাউজ: **{house.name}**\n"
            f"🔑 কোড: `{house.code}`\n\n"
            f"✅ আজকের মোট এক্টিভেশন: **{count}** টি\n"
            f"🕒 সর্বশেষ এক্টিভেশন: `{last_time}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 ডাটা অটো-সিঙ্ক হচ্ছে প্রতি ৫ মিনিট অন্তর।\n"
            f"⏰ রিপোর্ট সময়: {datetime.now().strftime('%I:%M %p')}"
        )

        # ইনলাইন বাটন (রিফ্রেশ করার জন্য)
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 রিফ্রেশ", callback_data=f"ga_hsel_{house.id}")
        builder.button(text="🔙 ব্যাকে যান", callback_data="ga_live_main")
        builder.adjust(2)

        # যদি মেসেজটি কলব্যাক থেকে আসে তবে এডিট করবে, নাহলে নতুন পাঠাবে
        try:
            await message.edit_text(report_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        except:
            await message.answer(report_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
