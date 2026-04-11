import logging
import sys
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from config.settings import BOT_TOKEN
from app.Services.db_service import init_db
from app.Middleware.access_control import ACLMiddleware
from app.Core.webhook_server import start_webhook_server

# --- ১. নতুন কোর অটোমেশন ইঞ্জিন ও সেশন ম্যানেজার ইম্পোর্ট ---
from app.Core.automation_engine import engine

# সিঙ্ক এবং রিসেট ফাংশনগুলো ইম্পোর্ট
from app.Services.Automation.Reports.ga_live import run_ga_live_sync, reset_daily_activations

# কন্ট্রোলার ইম্পোর্ট
from app.Controllers import (
    admin_controller, house_controller, user_controller,
    role_controller, automation_controller, sim_status_controller,
    sim_return_controller, sim_issue_controller, ga_live_controller,
)

# --- ২. লগিং কনফিগারেশন (সাইলেন্ট মুড) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# লাইব্রেরিগুলোর অপ্রয়োজনীয় লগ বন্ধ রাখা (শুধুমাত্র সিরিয়াস এরর দেখাবে)
logging.getLogger("aiogram").setLevel(logging.ERROR)
logging.getLogger("pyngrok").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("playwright").setLevel(logging.ERROR)
logging.getLogger("aiogram.dispatcher").setLevel(logging.CRITICAL)

# নিজস্ব মডিউলগুলোর জন্য INFO লেভেল নিশ্চিত করা
logging.getLogger("app.Core.login_manager").setLevel(logging.INFO)
logging.getLogger("app.Core.session_manager").setLevel(logging.INFO)
logging.getLogger("app.Core.automation_engine").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# ==========================================
# MASTER AUTOMATION SCHEDULER
# ==========================================

async def master_automation_scheduler():
    """
    একমাত্র মাস্টার লুপ যা সেশন পাহারাদার এবং জিএ সিঙ্ক উভয়ই হ্যান্ডেল করবে।
    সকাল ৮টা থেকে রাত ১২টা পর্যন্ত জিএ সিঙ্ক চলবে। 
    রাত ১২টায় রিসেট হবে।
    """
    logger.info("🚀 Master Automation Scheduler শুরু হয়েছে...")
    
    # সিস্টেম স্ট্যাবল হওয়ার জন্য কিছুক্ষণ অপেক্ষা
    await asyncio.sleep(20)

    while True:
        try:
            now = datetime.now()
            hour = now.hour

            # --- ১. রাত ১২টায় ডাটা রিসেট (00:00 - 00:05) ---
            if hour == 0 and now.minute < 5:
                logger.info("🧹 Midnight Reset: জিএ লাইভ টেবিল পরিষ্কার করা হচ্ছে...")
                await reset_daily_activations()
                await asyncio.sleep(300) # ৫ মিনিট বিরতি
                continue

            # --- ২. সিঙ্কিং টাইম (সকাল ৮টা থেকে রাত ১২টা) ---
            if 8 <= hour < 24:
                logger.info(f"🕒 [Job Started] সময়: {now.strftime('%I:%M %p')}")
                
                # সিঙ্ক রান করা (এটি প্রোফাইল ব্যবহার করবে এবং সেশন সচল রাখবে)
                # আলাদা ওয়াচার বা পিঙ্গারের প্রয়োজন নেই ✅
                await run_ga_live_sync()
                
                logger.info("✅ [Job Finished] পরবর্তী রান ৫ মিনিট পর।")
                await asyncio.sleep(300) # ৫ মিনিট বিরতি
            else:
                # রাত ১২টা থেকে সকাল ৮টা পর্যন্ত বিরতি
                logger.info(f"😴 Idle Time: এখন রাত {hour}টা। সকাল ৮টা পর্যন্ত বিরতি...")
                await asyncio.sleep(600) # ১০ মিনিট পর পর চেক করবে
                continue

        except Exception as e:
            logger.error(f"❌ [Master Scheduler Error] {str(e)}")
            await asyncio.sleep(60)

# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def main():
    # ১. ডাটাবেজ ইনিশিয়ালাইজেশন
    try:
        await init_db()
        print("✅ ডাটাবেজ কানেকশন সফল।")
    except Exception as e:
        print(f"❌ ডাটাবেজ কানেকশন এরর: {e}")
        return

    # ২. ব্রাউজার ইঞ্জিন স্টার্ট
    await engine.start()

    # ৩. বট এবং ডিসপ্যাচার সেটআপ
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.middleware(ACLMiddleware())

    # ৪. রাউটারগুলো রেজিস্টার করা
    dp.include_routers(
        admin_controller.router, house_controller.router,
        user_controller.router, role_controller.router,
        automation_controller.router, sim_status_controller.router,
        sim_return_controller.router, sim_issue_controller.router,
        ga_live_controller.router,
    )

    await bot.delete_webhook(drop_pending_updates=True)

    background_tasks = []
    try:
        # ওটিপি রিসিভার সার্ভার চালু রাখা
        webhook_task = asyncio.create_task(start_webhook_server(port=8080))
        
        # মাস্টার সিডিউলার চালু করা (এটি সিঙ্ক এবং সেশন দুটোই দেখবে) ✅
        scheduler_task = asyncio.create_task(master_automation_scheduler())
        
        background_tasks.extend([webhook_task, scheduler_task])

        logger.info("🤖 বট এবং মাস্টার অটোমেশন সিস্টেম সচল হয়েছে...")

        await dp.start_polling(bot)

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("👋 শাটডাউন শুরু হচ্ছে...")
        for task in background_tasks:
            task.cancel()
        await engine.stop()
        await bot.session.close()
        logger.info("✅ সবকিছু সফলভাবে বন্ধ করা হয়েছে।")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
