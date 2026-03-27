import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from config.settings import BOT_TOKEN
from app.Controllers import admin_controller, house_controller, role_controller
from app.Services.db_service import init_db

# লগিং কনফিগারেশন
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    # ১. ডাটাবেজ এবং টেবিল তৈরি নিশ্চিত করা
    try:
        await init_db()
        logger.info("ডাটাবেজ কানেকশন সফল হয়েছে।")
    except Exception as e:
        logger.error(f"ডাটাবেজ কানেকশন এরর: {e}")
        return

    # ২. বট এবং ডিসপ্যাচার সেটআপ
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ৩. রাউটারগুলো রেজিস্টার করা
    dp.include_router(admin_controller.router)
    dp.include_router(house_controller.router)
    dp.include_router(role_controller.router)

    # ৪. পুরানো পেন্ডিং মেসেজগুলো স্কিপ করা (বট অফ থাকাকালীন আসা মেসেজ)
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        logger.info("বট চালু হয়েছে এবং মেসেজ শোনার জন্য প্রস্তুত...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"বট চলাকালীন সমস্যা হয়েছে: {e}")
    finally:
        # ৫. ক্লিন শাটডাউন
        await bot.session.close()
        logger.info("বট সেশন ক্লোজ করা হয়েছে।")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Ctrl+C চাপলে এই অংশটি এরর না দেখিয়ে সুন্দরভাবে বন্ধ হবে
        logger.info("ইউজার দ্বারা বট বন্ধ করা হয়েছে।")
        sys.exit(0)
