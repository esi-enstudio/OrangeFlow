import logging
import sys
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from config.settings import BOT_TOKEN
from app.Services.db_service import init_db
from app.Middleware.access_control import ACLMiddleware
from app.Core.webhook_server import start_webhook_server
from app.Core.session_pinger import session_keeper_task

# সিঙ্ক এবং রিসেট ফাংশনগুলো ইম্পোর্ট করুন
from app.Services.Automation.Reports.ga_live import run_ga_live_sync, reset_daily_activations


# --- ১. লগিং কনফিগারেশন (স্মার্ট সাইলেন্ট মুড) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# লাইব্রেরিগুলোর ইন্টারনাল ফালতু লগগুলো বন্ধ রাখা (শুধুমাত্র সিরিয়াস এরর দেখাবে)
logging.getLogger("aiogram").setLevel(logging.ERROR)
logging.getLogger("pyngrok").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("playwright").setLevel(logging.ERROR)

# 🆕 এই লাইনটি বিশেষভাবে ওই লাল এররটি লুকানোর জন্য
logging.getLogger("aiogram.dispatcher").setLevel(logging.CRITICAL)

# আপনার নিজস্ব মডিউলগুলোর জন্য INFO লেভেল নিশ্চিত করা (যাতে এগুলো দেখা যায়)
logging.getLogger("app.Core.session_pinger").setLevel(logging.INFO)
logging.getLogger("app.Core.login_manager").setLevel(logging.INFO)
logging.getLogger("app.Core.otp_manager").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# কন্ট্রোলার ইম্পোর্ট
from app.Controllers import (
    admin_controller,
    house_controller,
    user_controller,
    role_controller,
    automation_controller, 
    sim_status_controller,
    sim_return_controller,
    sim_issue_controller,
    ga_live_controller,
)


# ==========================================
# GA LIVE SCHEDULER (ব্যাকগ্রাউন্ড লুপ)
# ==========================================

async def ga_live_scheduler_task():
    """
    ১. রাত ১২টায় ডাটা রিসেট করবে।
    ২. সকাল ৮টা থেকে রাত ১২টা পর্যন্ত ডাটা সিঙ্ক করবে।
    ৩. রাত ১২টা থেকে সকাল ৮টা পর্যন্ত বিরতি নিবে।
    """
    
    logging.info("🚀 GA Live Scheduler শুরু হয়েছে...")
    
    # বট চালুর পর প্রথম সিঙ্ক করার আগে ৬০ সেকেন্ড অপেক্ষা (সিস্টেম স্ট্যাবল হওয়ার জন্য)
    await asyncio.sleep(60)

    while True:
        try:
            now = datetime.now()
            hour = now.hour

            # --- ১. রাত ১২টায় রিসেট লজিক ---
            if hour == 0 and now.minute < 5:
                logging.info("🧹 Midnight Reset: জিএ লাইভ টেবিল পরিষ্কার করা হচ্ছে...")
                await reset_daily_activations()
                # রিসেট শেষে ৫ মিনিট ঘুমাবে যাতে একই লুপ বারবার রিসেট না দেয়
                await asyncio.sleep(300) 
                continue

            # --- ২. সময় নিয়ন্ত্রণ (সকাল ৮টার আগে কাজ করবে না) ---
            if hour < 8:
                # সকাল ৮টা পর্যন্ত প্রতি ১০ মিনিটে একবার চেক করবে সময় হয়েছে কি না
                logging.info(f"😴 Idle Time: এখন রাত {hour}টা। সকাল ৮টা পর্যন্ত বিরতি...")
                await asyncio.sleep(600) # ১০ মিনিট বিরতি
                continue

            # --- ৩. একটিভ সিঙ্ক (সকাল ৮টা থেকে রাত ১২টার আগ পর্যন্ত) ---
            logging.info(f"🕒 [Sync Active] সময়: {now.strftime('%I:%M %p')} | সিঙ্ক শুরু হচ্ছে...")
            await run_ga_live_sync()
            
            # ৫ মিনিট (৩০০ সেকেন্ড) বিরতি
            await asyncio.sleep(300)

        except Exception as e:
            logging.error(f"❌ [Scheduler Error] {str(e)}")
            # এরর হলে ১ মিনিট পর আবার ট্রাই করবে
            await asyncio.sleep(60)




# ==========================================
# MAIN ENTRY POINT
# ==========================================

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

    dp.include_routers(
        admin_controller.router, house_controller.router,
        user_controller.router, role_controller.router,
        automation_controller.router, sim_status_controller.router,
        sim_return_controller.router, sim_issue_controller.router,
        ga_live_controller.router,
    )

    # পুরানো পেন্ডিং মেসেজগুলো স্কিপ করা
    await bot.delete_webhook(drop_pending_updates=True)

    # সিডিউলারকে ব্যাকগ্রাউন্ড টাস্ক হিসেবে চালু করা ✅
    asyncio.create_task(ga_live_scheduler_task())

    # ব্যাকগ্রাউন্ড টাস্কগুলো ভেরিয়েবলে রাখা (বন্ধ করার সুবিধার জন্য)
    tasks = []

    try:
        # ব্যাকগ্রাউন্ড টাস্ক চালু করা
        webhook_task = asyncio.create_task(start_webhook_server(port=8080))
        keeper_task = asyncio.create_task(session_keeper_task())
        tasks.extend([webhook_task, keeper_task])

        logger.info("🤖 বট এবং ওটিপি সার্ভার সচল হয়েছে...")
        logger.info("💓 সেশন কিপার ব্যাকগ্রাউন্ডে চালু হয়েছে। (৫ মিনিট অন্তর চেক করবে)")

        # ৬. পোলিং শুরু
        await dp.start_polling(bot)

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.error(f"❌ বট চলাকালীন সমস্যা: {e}")
    finally:
        # ৭. গ্রেসফুল শাটডাউন (সবকিছু সুন্দরভাবে বন্ধ করা)
        logger.info("👋 শাটডাউন শুরু হচ্ছে...")
        
        # সব ব্যাকগ্রাউন্ড টাস্ক ক্যানসেল করা
        for task in tasks:
            task.cancel()
        
        # টাস্কগুলো বন্ধ হওয়া পর্যন্ত অপেক্ষা করা
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # বট সেশন ক্লোজ করা
        await bot.session.close()
        logger.info("✅ সবকিছু সফলভাবে বন্ধ করা হয়েছে। বিদায়!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # এখান থেকে শুধু প্রসেসটা ক্লিনলি বের হয়ে যাবে
        sys.exit(0)
