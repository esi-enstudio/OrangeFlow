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
        return

    logger.info(f"🕒 [GA Sync] শুরু হয়েছে {len(houses)}টি হাউজের জন্য...")

    for house in houses:
        try:
            # প্রতিটি হাউজের ডাটা আলাদাভাবে সিঙ্ক করা
            await sync_house_data(house)
            # প্রসেসিং গ্যাপ
            await asyncio.sleep(5) 
        except Exception as e:
            logger.error(f"❌ [GA Sync Error] {house.name}: {str(e)}")

async def sync_house_data(house):
    """সেশন ম্যানেজার (প্রোফাইল ভিত্তিক) ব্যবহার করে রিপোর্ট ডাউনলোড"""
    
    credentials = {
        "user": house.dms_user,
        "pass": house.dms_pass,
        "house_id": house.dms_house_id,
        "house_name": house.name,
        "code": house.code # প্রোফাইল ফোল্ডারের জন্য এটি জরুরি
    }

    # ১. সেশন ম্যানেজার থেকে সচল পেজ সংগ্রহ করা (এটি অটো-লগইন হ্যান্ডেল করবে)
    page, context = await session_manager.get_valid_page(credentials)
    
    file_path = os.path.join(TEMP_DIR, f"ga_{house.code}.xlsx")
    
    try:
        logger.info(f"🚀 [GA Sync] {house.name} রিপোর্ট ডাউনলোড করা হচ্ছে...")
        
        # ২. রিপোর্ট পেজে সরাসরি জাম্প
        await page.goto(REPORT_URL, wait_until="commit", timeout=40000)
        
        # ৩. তারিখ ইনপুট
        today_str = date.today().strftime("%Y-%m-%d")
        await page.fill("#StartDate", today_str)
        await page.fill("#EndDate", today_str)

        # ৪. ডাউনলোড প্রসেস
        async with page.expect_download() as download_info:
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        await download.save_as(file_path)

        # ৫. ডাটাবেজ আপডেট
        await process_and_save_data(file_path, house.id)
        
        logger.info(f"✅ [GA Sync] {house.name} সিঙ্ক সম্পন্ন।")

    finally:
        # কাজ শেষে শুধু পেজ এবং কন্টেক্সট বন্ধ করা
        # প্রোফাইল ফোল্ডারে ডাটা অটো-সেভ হয়ে যাবে
        await page.close()
        
        # টেম্প ফাইল ক্লিনআপ
        if os.path.exists(file_path):
            os.remove(file_path)

async def process_and_save_data(file_path, house_id):
    """NaN এরর হ্যান্ডলিং সহ ডাটা সেভ লজিক"""
    try:
        df = pd.read_excel(file_path, dtype=str)
        if df.empty:
            return

        # সকল খালি সেল এবং NaN ভ্যালু পরিষ্কার করা
        df = df.fillna("")
        df = df.replace({pd.NA: "", "nan": "", "NaN": ""})

        async with async_session() as session:
            # ইউনিক চেকের জন্য বর্তমান সিম লিস্ট লোড করা
            db_res = await session.execute(
                select(LiveActivation.sim_no).where(LiveActivation.house_id == house_id)
            )
            existing_sims = set(db_res.scalars().all())

            new_records = []
            for _, row in df.iterrows():
                sim_no = str(row.get('SIM_NO', '')).strip()
                
                if sim_no and sim_no not in existing_sims:
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
                        dh_lifting_date=str(row.get('DH_LIFTINGDATE', '')),
                        issue_date=str(row.get('ISSUEDATE', ''))
                    ))

            if new_records:
                session.add_all(new_records)
                await session.commit()
                logger.info(f"📊 [Sync] হাউজ {house_id}: {len(new_records)}টি নতুন এক্টিভেশন যুক্ত হয়েছে।")

    except Exception as e:
        logger.error(f"❌ [Data Error] {str(e)}")

async def reset_daily_activations():
    """রাত ১২টায় ডাটা ডিলিট করার লজিক"""
    async with async_session() as session:
        try:
            await session.execute(delete(LiveActivation))
            await session.commit()
            logger.info("🧹 [Reset] GA Live ডাটাবেজ ক্লিয়ার করা হয়েছে।")
        except Exception as e:
            logger.error(f"❌ [Reset Error] {str(e)}")