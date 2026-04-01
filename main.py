import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from config.settings import BOT_TOKEN
from app.Services.db_service import init_db
from app.Middleware.access_control import ACLMiddleware
from app.Core.webhook_server import start_webhook_server
from app.Core.session_pinger import session_keeper_task

# কন্ট্রোলার ইম্পোর্ট
from app.Controllers import (
    admin_controller,
    house_controller,
    user_controller,
    role_controller,
    automation_controller, 
    sim_status_controller,
    sim_return_controller
)

# --- ১. লগিং কনফিগারেশন (সাইলেন্ট মুড) ---
# মেইন লেভেল ERROR করা হয়েছে যাতে অপ্রয়োজনীয় INFO না আসে
logging.basicConfig(level=logging.ERROR) 

# লাইব্রেরিগুলোর ইন্টারনাল লগ পুরোপুরি বন্ধ করা
logging.getLogger("aiogram").setLevel(logging.ERROR)
logging.getLogger("pyngrok").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)

async def main():
    # ২. ডাটাবেজ এবং টেবিল তৈরি নিশ্চিত করা
    try:
        await init_db()
        print("✅ ডাটাবেজ কানেকশন সফল।")
    except Exception as e:
        print(f"❌ ডাটাবেজ কানেকশন এরর: {e}")
        return

    # ৩. বট এবং ডিসপ্যাচার সেটআপ
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ৪. মিডলওয়্যার এবং রাউটারগুলো রেজিস্টার করা
    # মিডলওয়্যারকে রাউটারগুলোর আগে রাখতে হয়
    dp.message.middleware(ACLMiddleware())
    
    dp.include_router(admin_controller.router)
    dp.include_router(house_controller.router)
    dp.include_router(user_controller.router)
    dp.include_router(role_controller.router)
    dp.include_router(automation_controller.router)
    dp.include_router(sim_status_controller.router)
    dp.include_router(sim_return_controller.router)

    # পুরানো পেন্ডিং মেসেজগুলো স্কিপ করা
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        # ওটিপি রিসিভার এবং এনগ্রোক সার্ভার চালু করা (একবারই কল হবে)
        asyncio.create_task(start_webhook_server(port=8080))

        # সেশন কিপার (Keep-Alive) ব্যাকগ্রাউন্ড টাস্ক চালু করা 🆕
        asyncio.create_task(session_keeper_task())

        print("🤖 বট এবং ওটিপি সার্ভার সচল হয়েছে...")
        print("💓 সেশন কিপার ব্যাকগ্রাউন্ডে চালু হয়েছে (৫ মিনিট অন্তর চেক করবে)।")
        
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ বট চলাকালীন সমস্যা: {e}")
    finally:
        # ক্লিন শাটডাউন
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 ইউজার দ্বারা বট বন্ধ করা হয়েছে।")
        sys.exit(0)