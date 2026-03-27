from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_house_list_keyboard(houses):
    builder = InlineKeyboardBuilder()

    for house in houses:
        # বাটনের টেক্সট হবে হাউজের নাম এবং ক্লিক করলে callback_data তে হাউজ আইডি যাবে
        builder.button(text=f"🏢 {house.name} ({house.code})", callback_data=f"view_house_{house.id}")

    builder.adjust(1)  # প্রতি লাইনে ১টি করে বাটন
    return builder.as_markup()