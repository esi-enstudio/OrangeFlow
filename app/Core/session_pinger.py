import asyncio
import os
import logging
from playwright.async_api import async_playwright
from datetime import datetime
from sqlalchemy import select

from app.Models.house import House
from app.Services.db_service import async_session
from app.Core.login_manager import dms_login

# লগার সেটআপ
logger = logging.getLogger(__name__)
SESSION_DIR = "sessions"

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def refresh_house_session(playwright, house):
    """একটি হাউজের সেশন চেক এবং প্রয়োজনে অটো-লগইন"""
    browser = None
    # সেশন ফাইল পাথ (লগইন ম্যানেজারের সাথে মিল রেখে)
    file_path = os.path.join(SESSION_DIR, f"session_{house.dms_user}.json")
    
    credentials = {
        "user": house.dms_user,
        "pass": house.dms_pass,
        "house_id": house.dms_house_id,
        "house_name": house.name
    }

    try:
        # ১. সেশন ফাইলসহ ব্রাউজার কন্টেক্সট তৈরি
        browser, context = await dms_login.get_browser_context(playwright, file_path)
        page = await context.new_page()
        
        logger.info(f"🔄 [Keep-Alive] Checking session for: {house.name}...")
        
        # ২. সেশন কি সচল আছে?
        is_valid = await dms_login.is_session_valid(page)
        
        if is_valid:
            # সচল সেশনটি আবার সেভ করা হচ্ছে মেয়াদী কুকি রিফ্রেশ করার জন্য
            await asyncio.sleep(2) # ছোট বিরতি
            await page.context.storage_state(path=file_path)
            print(f"[{get_now()}] ✅ [Still Active] {house.name} - সেশন সচল এবং ফাইল আপডেট হয়েছে।")
        else:
            # লগইন করার আগে পুরনো সেশন ফাইলটি ডিলিট করে দিন (যাতে ফ্রেশ লগইন হয়)
            if os.path.exists(file_path): os.remove(file_path)
            print(f"[{get_now()}] 🔑 [Session Lost] {house.name} - নতুন লগইন শুরু হচ্ছে...")
            await dms_login.perform_login(page, credentials, file_path)

    except Exception as e:
        logger.error(f"❌ [Keep-Alive Error] {house.name}: {str(e)}")
    finally:
        if browser:
            await browser.close()

async def session_keeper_task():
    """ব্যাকগ্রাউন্ড লুপ যা সব হাউজের সেশন কন্ট্রোল করবে"""
    # সেশন ডিরেক্টরি নিশ্চিত করা
    os.makedirs(SESSION_DIR, exist_ok=True)
    
    # বট পুরোপুরি চালু হওয়ার জন্য একটু বিরতি
    await asyncio.sleep(20)
    
    async with async_playwright() as p:
        while True:
            try:
                # ডাটাবেজ থেকে সব একটিভ হাউজ নেওয়া যাদের ডিএমএস ইউজার আছে
                async with async_session() as session:
                    result = await session.execute(
                        select(House).where(House.dms_user != None)
                    )
                    houses = result.scalars().all()

                if houses:
                    logger.info(f"🕒 [Keep-Alive] Starting heartbeat cycle for {len(houses)} houses...")
                    for house in houses:
                        await refresh_house_session(p, house)
                        # প্রতিটি হাউসের মাঝে ১০ সেকেন্ড বিরতি (ওটিপি জট এড়াতে)
                        await asyncio.sleep(10) 
                else:
                    logger.info("ℹ️ [Keep-Alive] No houses with DMS credentials found.")

                # ৪-৫ মিনিট পর পর পুনরায় চেক করবে (ডিএমএস সাধারণত ১০ মিনিটে আউট করে দেয়)
                logger.info("💤 [Keep-Alive] Cycle complete. Sleeping for 5 minutes...")
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"❌ [Keep-Alive Loop Error] {str(e)}")
                await asyncio.sleep(60)