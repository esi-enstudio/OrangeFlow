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
from app.Core.session_manager import session_manager

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
    ১. রাত ১২টায় ডাটাবেজ রিসেট করবে।
    ২. সকাল ৮টা থেকে রাত ১২টা পর্যন্ত ৫ মিনিট অন্তর GA সিঙ্ক করবে।
    """
    logger.info("🚀 Master Automation Scheduler শুরু হয়েছে...")
    
    # ওয়াচারকে প্রথম সাইকেল শেষ করার জন্য ৩ মিনিট সময় দেওয়া
    await asyncio.sleep(180)

    while True:
        try:
            now = datetime.now()
            hour = now.hour

            # --- ১. রাত ১২টায় রিসেট লজিক (00:00 - 00:05) ---
            if hour == 0 and now.minute < 5:
                logger.info("🧹 Midnight Reset: জিএ লাইভ টেবিল পরিষ্কার করা হচ্ছে...")
                await reset_daily_activations()
                await asyncio.sleep(300) # ৫ মিনিট বিরতি
                continue

            # --- ২. সময় নিয়ন্ত্রণ এবং সিঙ্ক (সকাল ৮টা থেকে রাত ১২টা) ---
            if 8 <= hour < 24:
                logger.info(f"🕒 [GA Sync Start] সময়: {now.strftime('%I:%M %p')}")
                
                # সিঙ্ক রান করা (এটি এখন গ্লোবাল ইঞ্জিন/প্রোফাইল ব্যবহার করবে)
                await run_ga_live_sync()
                
                logger.info("✅ [GA Sync Finished] পরবর্তী রান ৫ মিনিট পর।")
                await asyncio.sleep(300) # ৫ মিনিট বিরতি
            else:
                # রাত ১২টা থেকে সকাল ৮টা পর্যন্ত বিরতি
                logger.info(f"😴 Idle Time: এখন রাত {hour}টা। সকাল ৮টা পর্যন্ত সিঙ্ক বিরতি...")
                await asyncio.sleep(600) # ১০ মিনিট পর পর চেক করবে
                continue

        except Exception as e:
            logger.error(f"❌ [Scheduler Error] {str(e)}")
            await asyncio.sleep(60)

# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def main():
    # ১. ডাটাবেজ কানেকশন এবং টেবিল তৈরি নিশ্চিত করা
    try:
        await init_db()
        print("✅ ডাটাবেজ কানেকশন সফল।")
    except Exception as e:
        print(f"❌ ডাটাবেজ কানেকশন এরর: {e}")
        return

    # ২. গ্লোবাল ব্রাউজার ইঞ্জিন স্টার্ট করা (প্রোফাইল ভিত্তিক) ✅
    await engine.start()

    # ৩. বট এবং ডিসপ্যাচার সেটআপ
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ৪. মিডলওয়্যার এবং রাউটার রেজিস্ট্রেশন
    dp.message.middleware(ACLMiddleware())

    dp.include_routers(
        admin_controller.router, house_controller.router,
        user_controller.router, role_controller.router,
        automation_controller.router, sim_status_controller.router,
        sim_return_controller.router, sim_issue_controller.router,
        ga_live_controller.router,
    )

    # পুরানো পেন্ডিং মেসেজ স্কিপ করা (বট অফ থাকাকালীন মেসেজ)
    await bot.delete_webhook(drop_pending_updates=True)

    background_tasks = []
    try:
        # ৫. ব্যাকগ্রাউন্ড টাস্কগুলো চালু করা
        
        # ওটিপি রিসিভার সার্ভার (ম্যাক্রোড্রয়েড ও এনগ্রোকের জন্য)
        webhook_task = asyncio.create_task(start_webhook_server(port=8080))
        
        # সেশন পাহারাদার (এটি নিয়মিত সব হাউজের সেশন প্রোফাইল চেক ও রিফ্রেশ করবে) ✅
        watcher_task = asyncio.create_task(session_manager.background_watcher())
        
        # মাস্টার সিডিউলার (আপনার রিকোয়েস্ট অনুযায়ী আপাতত কমেন্ট করা হলো)
        scheduler_task = asyncio.create_task(master_automation_scheduler())
        
        background_tasks.extend([webhook_task, watcher_task, scheduler_task])

        logger.info("🤖 বট, ওটিপি সার্ভার এবং সেশন ওয়াচার সচল হয়েছে...")

        # ৬. বটের পোলিং শুরু
        await dp.start_polling(bot)

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.error(f"❌ বট চলাকালীন সমস্যা: {e}")
    finally:
        # ৭. গ্রেসফুল শাটডাউন
        logger.info("👋 শাটডাউন শুরু হচ্ছে...")
        
        # সব ব্যাকগ্রাউন্ড টাস্ক বন্ধ করা
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        
        # ইঞ্জিন বন্ধ করা (Chrome প্রোফাইল প্রসেস কিল করা) ✅
        await engine.stop()
        
        # বট সেশন ক্লোজ করা
        await bot.session.close()
        logger.info("✅ সবকিছু সফলভাবে বন্ধ করা হয়েছে।")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # এখান থেকে শুধু প্রসেসটা ক্লিনলি বের হয়ে যাবে
        sys.exit(0)