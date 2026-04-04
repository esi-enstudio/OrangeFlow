import asyncio
import os
import logging
from playwright.async_api import async_playwright
from datetime import datetime
from sqlalchemy import select

from app.Models.house import House
from app.Services.db_service import async_session
from app.Core.login_manager import dms_login

# লগিং কনফিগারেশন
logger = logging.getLogger(__name__)

# সেশন ডিরেক্টরি নিশ্চিত করা
SESSION_DIR = "sessions"
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

def get_now():
    """টার্মিনালে দেখানোর জন্য বর্তমান সময়"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def refresh_house_session(playwright, house):
    """একটি নির্দিষ্ট হাউজের সেশন চেক এবং প্রয়োজনে অটো-লগইন"""
    browser = None
    # সেশন ফাইলের নাম (login_manager এর সাথে মিল রেখে)
    session_file = f"session_{house.dms_user}.json"
    file_path = os.path.join(SESSION_DIR, session_file)
    
    credentials = {
        "user": house.dms_user,
        "pass": house.dms_pass,
        "house_id": house.dms_house_id,
        "house_name": house.name,
        "code": house.code
    }

    try:
        # ১. হাউজ ভিত্তিক ব্রাউজার কন্টেক্সট জেনারেট করা
        browser, context = await dms_login.get_browser_context(playwright, file_path)
        page = await context.new_page()
        
        logger.info(f"🔄 [Keep-Alive] Checking session: {house.name}")
        
        # ২. বর্তমান সেশনটি কি কাজ করছে?
        is_valid = await dms_login.is_session_valid(page)
        
        if is_valid:
            # সেশন সচল থাকলে কুকি রিফ্রেশ করে সেভ করা
            await page.context.storage_state(path=file_path)
            logger.info(f"✅ [Keep-Alive] Session ACTIVE for {house.name}")
        else:
            # সেশন এক্সপায়ার করলে নতুন করে লগইন ট্রাই করা
            logger.warning(f"⚠️ [Keep-Alive] Session EXPIRED for {house.name}. Triggering Auto-Login...")
            
            # এটি আপনার ওটিপি ম্যানেজারের মাধ্যমে ম্যাক্রোড্রয়েড ওটিপির জন্য ওয়েট করবে
            login_success = await dms_login.perform_login(page, credentials, file_path)
            
            if login_success:
                logger.info(f"🎊 [Keep-Alive] Auto-Login SUCCESSFUL for {house.name}")
            else:
                logger.error(f"❌ [Keep-Alive] Auto-Login FAILED for {house.name}. Will try again later.")

    except Exception as e:
        logger.error(f"❌ [Keep-Alive Error] Error processing {house.name}: {str(e)}")
    finally:
        if browser:
            await browser.close()

async def session_keeper_task():
    """সব হাউজের জন্য ব্যাকগ্রাউন্ড সেশন রিফ্রেশার লুপ"""
    # বট স্টার্ট হওয়ার পর কিছুক্ষণ বিরতি (সিস্টেম স্ট্যাবল হওয়ার জন্য)
    await asyncio.sleep(10)
    logger.info("💓 Session Keeper task has started.")
    
    async with async_playwright() as p:
        while True:
            try:
                # ডাটাবেজ থেকে সব হাউজ নেওয়া যাদের DMS ক্রেডেনশিয়াল আছে
                async with async_session() as session:
                    result = await session.execute(
                        select(House).where(House.dms_user != None)
                    )
                    houses = result.scalars().all()

                if houses:
                    logger.info(f"🕒 [Keep-Alive] Starting heartbeat cycle for {len(houses)} houses...")
                    for house in houses:
                        # প্রতিটি হাউজের সেশন আলাদাভাবে প্রসেস হবে
                        await refresh_house_session(p, house)
                        # প্রতিটি হাউসের মাঝে ছোট বিরতি (যাতে একসাথে অনেক ওটিপি না আসে)
                        await asyncio.sleep(10) 
                else:
                    logger.info("ℹ️ [Keep-Alive] No houses found with DMS credentials.")

                # ৫ মিনিট (৩০০ সেকেন্ড) পর পর রিফ্রেশ করবে
                logger.info("💤 [Keep-Alive] Cycle complete. Sleeping for 5 minutes...")
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"❌ [Keep-Alive Loop Error] {str(e)}")
                # এরর হলে ১ মিনিট পর আবার ট্রাই করবে
                await asyncio.sleep(60)