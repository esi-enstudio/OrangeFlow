import os
import asyncio
import logging
import pandas as pd
import warnings
from datetime import date, datetime
from sqlalchemy import select, delete

# কোর মডিউল ইম্পোর্ট
from app.Models.house import House
from app.Models.live_activation import LiveActivation
from app.Services.db_service import async_session
from app.Core.session_manager import session_manager

# openpyxl ওয়ার্নিং সাইলেন্ট করা
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

REPORT_URL = "https://blkdms.banglalink.net/ActivationReport"
TEMP_DIR = "temp_downloads"

logger = logging.getLogger("app.Services.Automation.GA")

async def run_ga_live_sync():
    """সবগুলো হাউজের জন্য জিএ লাইভ ডাটা সিঙ্ক করার মেইন ফাংশন"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    async with async_session() as session:
        # শুধুমাত্র যাদের DMS ক্রেডেনশিয়াল আছে তাদের তথ্য নেওয়া
        result = await session.execute(select(House).where(House.dms_user != None))
        houses = result.scalars().all()

    if not houses:
        logger.info("ℹ️ সিঙ্ক করার মতো কোনো হাউজ পাওয়া যায়নি।")
        return

    logger.info(f"🕒 [GA Sync] শুরু হয়েছে {len(houses)}টি হাউজের জন্য...")

    for house in houses:
        try:
            # প্রতিটি হাউজের ডাটা আলাদাভাবে সিঙ্ক করা
            await sync_house_data(house)
            # প্রসেসিং গ্যাপ যাতে ডিএমএস ব্লক না করে
            await asyncio.sleep(5) 
        except Exception as e:
            logger.error(f"❌ [GA Sync Error] {house.name}: {str(e)}")

async def sync_house_data(house):
    """সেশন ম্যানেজার ব্যবহার করে রিপোর্ট ডাউনলোড"""
    
    credentials = {
        "user": house.dms_user,
        "pass": house.dms_pass,
        "house_id": house.dms_house_id,
        "house_name": house.name,
        "code": house.code
    }

    # ১. সেশন ম্যানেজার থেকে সচল পেজ সংগ্রহ
    page, context = await session_manager.get_valid_page(credentials)
    
    file_path = os.path.join(TEMP_DIR, f"ga_{house.code}.xlsx")
    
    try:
        logger.info(f"🚀 [GA Sync] {house.name} রিপোর্ট ডাউনলোড শুরু হচ্ছে...")
        
        # ২. রিপোর্ট পেজে যাওয়া (domcontentloaded বেশি স্ট্যাবল)
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=60000)
        
        # ৩. তারিখ ফিল্ড আসা পর্যন্ত অপেক্ষা এবং ইনপুট
        await page.wait_for_selector("#StartDate", timeout=30000)
        
        today_str = date.today().strftime("%Y-%m-%d")
        
        # সরাসরি টাইপ করার বদলে evaluate ব্যবহার করা নিরাপদ তারিখের জন্য
        await page.evaluate(f"document.getElementById('StartDate').value = '{today_str}';")
        await page.evaluate(f"document.getElementById('EndDate').value = '{today_str}';")
        
        await asyncio.sleep(1) # ইনপুট প্রসেসিং গ্যাপ

        # ৪. ডাউনলোড প্রসেস (Export Details বাটনে ক্লিক)
        async with page.expect_download() as download_info:
            # বাটনটি দৃশ্যমান হওয়া পর্যন্ত অপেক্ষা
            await page.wait_for_selector("button:has-text('Export Details')", state="visible")
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        await download.save_as(file_path)

        # ৫. ডাটাবেজ আপডেট কল করা
        await process_and_save_data(file_path, house.id)
        
        logger.info(f"✅ [GA Sync] {house.name} ডাটাবেজ আপডেট সফল।")

    finally:
        # ৬. কাজ শেষে ট্যাব এবং কন্টেক্সট বন্ধ করা ✅
        if page:
            await page.close()
        if context:
            await context.close()
        
        # এখানে 'house_name' এর বদলে 'house.name' ব্যবহার করা হয়েছে ✅
        logger.info(f"🚪 [{house.name}] টাস্ক ক্লিনআপ সম্পন্ন।")

        
        # টেম্প ফাইল ক্লিনআপ
        if os.path.exists(file_path):
            os.remove(file_path)

async def process_and_save_data(file_path, house_id):
    """সবগুলো কলাম ম্যাপ করে ডাটা সেভ করার লজিক"""
    try:
        # ফাইল রিড করা
        df = pd.read_excel(file_path, dtype=str)
        if df.empty:
            logger.info(f"ℹ️ {file_path} ফাইলে কোনো ডাটা পাওয়া যায়নি।")
            return

        # সকল NaN এবং খালি ভ্যালু পরিষ্কার করা
        df = df.fillna("")
        df = df.replace({pd.NA: "", "nan": "", "NaN": ""})

        async with async_session() as session:
            # বর্তমান ডাটাবেজের আজকের সব SIM_NO সংগ্রহ (ডুপ্লিকেট এড়াতে)
            db_res = await session.execute(
                select(LiveActivation.sim_no).where(LiveActivation.house_id == house_id)
            )
            existing_sims = set(db_res.scalars().all())

            new_records = []
            for _, row in df.iterrows():
                # সামনে-পেছনে স্পেস থাকলে পরিষ্কার করা
                sim_no = str(row.get('SIM_NO', '')).strip()
                
                if sim_no and sim_no not in existing_sims:
                    # পূর্ণাঙ্গ কলাম ম্যাপিং (আপনার রিকোয়েস্ট অনুযায়ী)
                    new_records.append(LiveActivation(
                        house_id=house_id,
                        activation_date=str(row.get('ACTIVATION_DATE', '')),
                        activation_time=str(row.get('ACTIVATION_TIME', '')),
                        retailer_code=str(row.get('RETAILER_CODE', '')),
                        retailer_name=str(row.get('RETAILER_NAME', '')),
                        bts_code=str(row.get('BTS_CODE', '')),
                        thana=str(row.get('THANA', '')),
                        promotion=str(row.get('PROMOTION', '')),
                        product_code=str(row.get('PRODUCT_CODE', '')),
                        product_name=str(row.get('PRODUCT_NAME', '')),
                        sim_no=sim_no,
                        msisdn=str(row.get('MSISDN', '')),
                        selling_price=str(row.get('SELLING_PRICE', '')),
                        bp_flag=str(row.get('BP_FLAG', '')),
                        bp_number=str(row.get('BP_NUMBER', '')),
                        fc_bts_code=str(row.get('FC_BTS_CODE', '')),
                        bio_bts_code=str(row.get('BIO_BTS_CODE', '')),
                        dh_lifting_date=str(row.get('DH_LIFTINGDATE', '')),
                        issue_date=str(row.get('ISSUEDATE', '')),
                        subscription_type=str(row.get('SUBSCRIPTION_TYPE', '')),
                        service_class=str(row.get('SERVICE_CLASS', '')),
                        customer_second_contact=str(row.get('CUSTOMER_SECOND_CONTACT', ''))
                    ))

            if new_records:
                session.add_all(new_records)
                await session.commit()
                logger.info(f"📊 [Database] হাউজ আইডি {house_id}: {len(new_records)}টি ইউনিক ডাটা যুক্ত হয়েছে।")
            else:
                logger.info(f"ℹ️ হাউজ আইডি {house_id}: নতুন কোনো ডাটা নেই।")

    except Exception as e:
        logger.error(f"❌ [Process Error] ডাটা প্রসেসিং সমস্যা: {str(e)}")

async def reset_daily_activations():
    """রাত ১২টায় ডাটা ডিলিট করার লজিক"""
    async with async_session() as session:
        try:
            await session.execute(delete(LiveActivation))
            await session.commit()
            logger.info("🧹 [Reset] Live Activation টেবিল সফলভাবে পরিষ্কার করা হয়েছে।")
        except Exception as e:
            logger.error(f"❌ [Reset Error] ডাটা রিসেট ব্যর্থ: {str(e)}")