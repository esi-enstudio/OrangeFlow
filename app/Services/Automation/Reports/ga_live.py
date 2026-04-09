import os
import asyncio
import logging
import pandas as pd
from datetime import date, datetime
from playwright.async_api import async_playwright
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

# আপনার প্রজেক্টের মডিউল ইম্পোর্ট
from app.Models.house import House
from app.Models.live_activation import LiveActivation
from app.Services.db_service import async_session
from app.Core.login_manager import dms_login

# কনফিগারেশন
REPORT_URL = "https://blkdms.banglalink.net/ActivationReport"
TEMP_DIR = "temp_downloads"

logger = logging.getLogger(__name__)

async def run_ga_live_sync():
    """সবগুলো হাউজের জন্য জিএ লাইভ ডাটা সিঙ্ক করার মেইন ফাংশন"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    async with async_session() as session:
        # শুধুমাত্র যাদের DMS ক্রেডেনশিয়াল আছে তাদের তথ্য নেওয়া
        result = await session.execute(select(House).where(House.dms_user != None))
        houses = result.scalars().all()

    if not houses:
        logger.info("ℹ️ কোনো হাউজ পাওয়া যায়নি যাদের DMS ক্রেডেনশিয়াল সেট করা আছে।")
        return

    logger.info(f"🕒 GA Live Sync শুরু হয়েছে {len(houses)}টি হাউজের জন্য...")

    async with async_playwright() as p:
        for house in houses:
            try:
                await sync_house_data(p, house)
            except Exception as e:
                logger.error(f"❌ Error syncing house {house.name}: {str(e)}")
            # হাউজগুলোর মাঝে ছোট গ্যাপ যাতে DMS সার্ভার ব্লক না করে
            await asyncio.sleep(5)

async def sync_house_data(playwright, house):
    """একটি নির্দিষ্ট হাউজের ডাটা ডাউনলোড এবং ডাটাবেজ আপডেট"""
    session_file = f"sessions/session_{house.dms_user}.json"
    
    # ব্রাউজার লঞ্চ
    browser, context = await dms_login.get_browser_context(playwright, session_file)
    page = await context.new_page()
    
    try:
        # ১. সেশন চেক ও লগইন
        if not await dms_login.is_session_valid(page):
            credentials = {
                "user": house.dms_user,
                "pass": house.dms_pass,
                "house_id": house.dms_house_id,
                "house_name": house.name,
                "code": house.code
            }
            if not await dms_login.perform_login(page, credentials, session_file):
                logger.error(f"⚠️ {house.name} এ লগইন করা সম্ভব হয়নি।")
                return

        # ২. রিপোর্ট পেজে যাওয়া এবং ডাউনলোড করা
        await page.goto(REPORT_URL)
        await page.wait_for_selector("#StartDate")
        
        today_str = date.today().strftime("%Y-%m-%d")
        await page.fill("#StartDate", today_str)
        await page.fill("#EndDate", today_str)

        async with page.expect_download() as download_info:
            # Export Details বাটনে ক্লিক
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        file_path = os.path.join(TEMP_DIR, f"ga_{house.code}.xlsx")
        await download.save_as(file_path)

        # ৩. ডাটা প্রসেসিং ও ডাটাবেজ আপডেট
        await process_and_save_data(file_path, house.id)

    finally:
        await browser.close()
        if os.path.exists(file_path):
            os.remove(file_path)

async def process_and_save_data(file_path, house_id):
    """এক্সেল ফাইল থেকে ডাটা নিয়ে ডাটাবেজে ইউনিক চেক করে সেভ করা"""
    try:
        # ১. ফাইল পড়া (dtype=str দিয়ে শুরুতেই সব স্ট্রিং করার চেষ্টা করা)
        df = pd.read_excel(file_path, dtype=str)
        
        if df.empty:
            return

        # ২. অত্যন্ত গুরুত্বপূর্ণ: সকল NaN (খালি সেল) কে খালি স্ট্রিং "" দিয়ে বদলে দেওয়া ✅
        # এটি আপনার 'nan (expected str, got float)' এররটি সমাধান করবে।
        df = df.replace({pd.NA: "", "nan": "", "NaN": ""})
        df = df.fillna("")

        async with async_session() as session:
            # বর্তমান ডাটাবেজে থাকা আজকের SIM_NO এর সেট নেওয়া
            db_res = await session.execute(
                select(LiveActivation.sim_no).where(LiveActivation.house_id == house_id)
            )
            existing_sims = set(db_res.scalars().all())

            new_objects = []
            for _, row in df.iterrows():
                # সিরিয়াল ক্লিন করা
                sim_no = str(row.get('SIM_NO', '')).strip()
                
                # যদি সিরিয়ালটি খালি না হয় এবং ডাটাবেজে আগে থেকে না থাকে
                if sim_no and sim_no not in existing_sims:
                    # প্রতিটি ভ্যালু নিশ্চিতভাবে স্ট্রিং হিসেবে নেওয়া এবং 'nan' চেক করা
                    def clean(val):
                        v = str(val).strip()
                        return "" if v.lower() == "nan" else v

                    new_activation = LiveActivation(
                        house_id=house_id,
                        activation_date=clean(row.get('ACTIVATION_DATE')),
                        activation_time=clean(row.get('ACTIVATION_TIME')),
                        retailer_code=clean(row.get('RETAILER_CODE')),
                        retailer_name=clean(row.get('RETAILER_NAME')),
                        bts_code=clean(row.get('BTS_CODE')),
                        thana=clean(row.get('THANA')),
                        promotion=clean(row.get('PROMOTION')),
                        product_code=clean(row.get('PRODUCT_CODE')),
                        product_name=clean(row.get('PRODUCT_NAME')),
                        sim_no=sim_no,
                        msisdn=clean(row.get('MSISDN')),
                        selling_price=clean(row.get('SELLING_PRICE')),
                        bp_flag=clean(row.get('BP_FLAG')),
                        bp_number=clean(row.get('BP_NUMBER')),
                        fc_bts_code=clean(row.get('FC_BTS_CODE')),
                        bio_bts_code=clean(row.get('BIO_BTS_CODE')),
                        dh_lifting_date=clean(row.get('DH_LIFTINGDATE')),
                        issue_date=clean(row.get('ISSUEDATE')),
                        subscription_type=clean(row.get('SUBSCRIPTION_TYPE')),
                        service_class=clean(row.get('SERVICE_CLASS')),
                        customer_second_contact=clean(row.get('CUSTOMER_SECOND_CONTACT'))
                    )
                    new_objects.append(new_activation)

            # ৫. বাল্ক ইনসার্ট
            if new_objects:
                session.add_all(new_objects)
                await session.commit()
                logger.info(f"✅ House ID {house_id}: {len(new_objects)}টি নতুন ডাটা সিঙ্ক হয়েছে।")
            else:
                logger.info(f"ℹ️ House ID {house_id}: কোনো নতুন ডাটা পাওয়া যায়নি।")

    except Exception as e:
        logger.error(f"❌ ডাটা প্রসেসিং এরর: {str(e)}")

async def reset_daily_activations():
    """রাত ১২টায় টেবিল ক্লিয়ার করার ফাংশন"""
    async with async_session() as session:
        try:
            await session.execute(delete(LiveActivation))
            await session.commit()
            logger.info("🧹 [Cleanup] GA Live টেবিলের সকল ডাটা মুছে ফেলা হয়েছে (Daily Reset)।")
        except Exception as e:
            logger.error(f"❌ [Cleanup Error] ডাটা মুছতে সমস্যা হয়েছে: {e}")