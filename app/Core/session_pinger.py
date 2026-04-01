import asyncio
import os
from playwright.async_api import async_playwright
from datetime import datetime
from sqlalchemy import select

from app.Models.house import House
from app.Services.db_service import async_session
from app.Core.login_manager import dms_login

# সেশন ফাইলের ডিরেক্টরি
SESSION_DIR = "sessions"

def get_now():
    """টার্মিনালে দেখানোর জন্য বর্তমান সময়"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def refresh_house_session(playwright, house):
    """একটি হাউজের সেশন চেক এবং প্রয়োজনে অটো-লগইন"""
    browser = None
    session_file = f"session_{house.dms_user}.json"
    file_path = os.path.join(SESSION_DIR, session_file)
    
    # অটোমেশনের জন্য ক্রেডেনশিয়াল ফরম্যাট করা
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
        
        print(f"[{get_now()}] 🔄 [Keep-Alive] Checking session for: {house.name}...")
        
        # ২. সেশন কি ভ্যালিড?
        is_valid = await dms_login.is_session_valid(page)
        
        if is_valid:
            # সেশন ভালো থাকলে জাস্ট স্টেট সেভ করে মেয়াদ বাড়ানো
            await page.context.storage_state(path=file_path)
            print(f"[{get_now()}] ✅ [Keep-Alive] Session is ACTIVE for {house.name}. State updated.")
        else:
            # সেশন এক্সপায়ার হলে অটোমেটিক ওটিপি প্রসেস ট্রিগার করা
            print(f"[{get_now()}] ⚠️ [Keep-Alive] Session EXPIRED for {house.name}. Attempting Auto-Login...")
            
            # এটি আপনার ম্যাক্রোড্রয়েড ওটিপির জন্য অপেক্ষা করবে
            login_success = await dms_login.perform_login(page, credentials, file_path)
            
            if login_success:
                print(f"[{get_now()}] 🎊 [Keep-Alive] Auto-Login SUCCESSFUL for {house.name}.")
            else:
                print(f"[{get_now()}] ❌ [Keep-Alive] Auto-Login FAILED for {house.name}. Will retry next cycle.")

    except Exception as e:
        print(f"[{get_now()}] ❌ [Keep-Alive Error] Error processing {house.name}: {str(e)}")
    finally:
        if browser:
            await browser.close()

async def session_keeper_task():
    """ব্যাকগ্রাউন্ড লুপ যা সব হাউজের সেশন কন্ট্রোল করবে"""
    # বট পুরোপুরি চালু হওয়ার জন্য একটু বিরতি
    await asyncio.sleep(15)
    
    async with async_playwright() as p:
        while True:
            try:
                # ডাটাবেজ থেকে সব হাউজ নেওয়া যাদের ডিএমএস ইউজার আছে
                async with async_session() as session:
                    result = await session.execute(
                        select(House).where(House.dms_user != None)
                    )
                    houses = result.scalars().all()

                if houses:
                    print(f"[{get_now()}] 🕒 [Keep-Alive] Starting heartbeat cycle for {len(houses)} houses...")
                    for house in houses:
                        await refresh_house_session(p, house)
                        # প্রতিটি হাউসের মাঝে ছোট বিরতি যাতে ওটিপি কনফ্লিক্ট না হয়
                        await asyncio.sleep(10) 
                else:
                    print(f"[{get_now()}] ℹ️ [Keep-Alive] No houses found with DMS credentials.")

                # ৫ মিনিট পর পর পুনরায় চেক করবে
                print(f"[{get_now()}] 💤 [Keep-Alive] Sleeping for 5 minutes...")
                await asyncio.sleep(300)

            except Exception as e:
                print(f"[{get_now()}] ❌ [Keep-Alive Loop Error] {str(e)}")
                await asyncio.sleep(60)