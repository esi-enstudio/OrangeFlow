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
from app.Models.retailer import Retailer

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
    """সবগুলো কলাম ম্যাপ করে এবং রিটেইলার আইডি লিঙ্ক করে ডাটা সেভ করার লজিক"""
    try:
        # ১. ফাইল রিড করা
        df = pd.read_excel(file_path, dtype=str)
        if df.empty:
            logger.info(f"ℹ️ {file_path} ফাইলে কোনো ডাটা পাওয়া যায়নি।")
            return

        # ২. সকল NaN এবং খালি ভ্যালু পরিষ্কার করা
        df = df.fillna("")
        df = df.replace({pd.NA: "", "nan": "", "NaN": ""})

        async with async_session() as session:
            # ৩. ফাস্ট পারফরম্যান্সের জন্য ওই হাউজের সকল রিটেইলারের কোড এবং আইডি ম্যাপ তৈরি করা ✅
            ret_res = await session.execute(
                select(Retailer.retailer_code, Retailer.id).where(Retailer.house_id == house_id)
            )
            # ডিকশনারি ফরম্যাট: {"R12345": 10, "R54321": 11}
            retailer_map = {str(r.retailer_code).strip(): r.id for r in ret_res.all()}

            # ৪. বর্তমান ডাটাবেজের আজকের সব SIM_NO সংগ্রহ (ডুপ্লিকেট এড়াতে)
            db_res = await session.execute(
                select(LiveActivation.sim_no).where(LiveActivation.house_id == house_id)
            )
            existing_sims = set(db_res.scalars().all())

            new_records = []
            for _, row in df.iterrows():
                sim_no = str(row.get('SIM_NO', '')).strip()
                ret_code = str(row.get('RETAILER_CODE', '')).strip()
                
                # ৫. ইউনিক চেক: যদি সিমটি আগে থেকে ডাটাবেজে না থাকে
                if sim_no and sim_no not in existing_sims:
                    
                    # ৬. রিটেইলার আইডি খুঁজে বের করা (ম্যাপ থেকে) ✅
                    # যদি রিটেইলার লিস্টে এই কোড না থাকে, তবে এটি None থাকবে
                    retailer_db_id = retailer_map.get(ret_code)

                    # হেল্পার ফাংশন: ডাটা ক্লিন এবং স্ট্রিং নিশ্চিত করতে
                    def get_val(key):
                        return str(row.get(key, '')).strip()

                    new_activation = LiveActivation(
                        house_id=house_id,
                        retailer_id=retailer_db_id, # রিটেইলার টেবিলের ফরেন-কি ✅
                        
                        activation_date=get_val('ACTIVATION_DATE'),
                        activation_time=get_val('ACTIVATION_TIME'),
                        retailer_code=ret_code, # টেক্সট কোডটিও ব্যাকআপ হিসেবে থাকবে
                        retailer_name=get_val('RETAILER_NAME'),
                        bts_code=get_val('BTS_CODE'),
                        thana=get_val('THANA'),
                        promotion=get_val('PROMOTION'),
                        product_code=get_val('PRODUCT_CODE'),
                        product_name=get_val('PRODUCT_NAME'),
                        sim_no=sim_no,
                        msisdn=get_val('MSISDN'),
                        selling_price=get_val('SELLING_PRICE'),
                        bp_flag=get_val('BP_FLAG'),
                        bp_number=get_val('BP_NUMBER'),
                        fc_bts_code=get_val('FC_BTS_CODE'),
                        bio_bts_code=get_val('BIO_BTS_CODE'),
                        dh_lifting_date=get_val('DH_LIFTINGDATE'),
                        issue_date=get_val('ISSUEDATE'),
                        subscription_type=get_val('SUBSCRIPTION_TYPE'),
                        service_class=get_val('SERVICE_CLASS'),
                        customer_second_contact=get_val('CUSTOMER_SECOND_CONTACT')
                    )
                    new_records.append(new_activation)

            # ৭. বাল্ক ইনসার্ট করা
            if new_records:
                session.add_all(new_records)
                await session.commit()
                logger.info(f"📊 [Sync] হাউজ আইডি {house_id}: {len(new_records)}টি নতুন ডাটা যুক্ত হয়েছে।")
            else:
                logger.info(f"ℹ️ হাউজ আইডি {house_id}: নতুন কোনো ডাটা পাওয়ার যায়নি।")

    except Exception as e:
        logger.error(f"❌ [Process Error] ডাটা প্রসেসিং সমস্যা: {str(e)}", exc_info=True)










async def reset_daily_activations():
    """রাত ১২টায় ডাটা ডিলিট করার লজিক"""
    async with async_session() as session:
        try:
            await session.execute(delete(LiveActivation))
            await session.commit()
            logger.info("🧹 [Reset] Live Activation টেবিল সফলভাবে পরিষ্কার করা হয়েছে।")
        except Exception as e:
            logger.error(f"❌ [Reset Error] ডাটা রিসেট ব্যর্থ: {str(e)}")