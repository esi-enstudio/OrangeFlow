import asyncio
import os
import shutil
import logging
import time
import pandas as pd
import xlwings as xw
from datetime import date, datetime
from sqlalchemy import select

# কোর মডিউল ইম্পোর্ট
from app.Core.session_manager import session_manager
from app.Services.db_service import async_session
from app.Models.house import House

logger = logging.getLogger("app.ExternalSync")

# লোকাল কনফিগারেশন
LOCAL_CONFIG = {
    "MYMVAI01": {
        "master_path": r"G:\My Drive\BL\RSO\UC\2026\04_UC_April'26.xlsb",
        "master_sheet": "Activations Live Raw",
        "wa_group": "GuagYPexjY0IM3YdUSyBi2",
        "wa_sheet": "RS0 GA Live",
        "wa_range": "A1:L31"
    },
    "MYMVAI02": {
        "master_path": r"G:\My Drive\BL\RSO\UC\2026\04_UC_April'26 - MYMVAI02.xlsb",
        "master_sheet": "Activations Live Raw",
        "wa_group": "CD9KgPa9JxN21rgGDKBF2J", 
        "wa_sheet": "RS0 GA Live",
        "wa_range": "A1:J16"
    }
}

REPORT_URL = "https://blkdms.banglalink.net/ActivationReport"
DOWNLOAD_DIR = "temp_downloads"

async def run_excel_wa_sync():
    """মাস্টার সিডিউলার থেকে কল হবে"""
    if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)

    async with async_session() as session:
        house_codes = list(LOCAL_CONFIG.keys())
        result = await session.execute(select(House).where(House.code.in_(house_codes)))
        houses = result.scalars().all()

    for house in houses:
        try:
            config = LOCAL_CONFIG.get(house.code)
            await process_excel_wa_task(house, config)
        except Exception as e:
            logger.error(f"❌ {house.name} সিঙ্ক এরর: {e}")
        await asyncio.sleep(5)

async def process_excel_wa_task(house, config):
    credentials = {
        "user": house.dms_user, "pass": house.dms_pass,
        "house_id": house.dms_house_id, "house_name": house.name, "code": house.code
    }

    # সেশন ম্যানেজার থেকে পেজ নেওয়া
    page, context = await session_manager.get_valid_page(credentials)
    file_path = os.path.join(DOWNLOAD_DIR, f"ga_{house.code}.xlsx")
    image_path = os.path.join(DOWNLOAD_DIR, f"ss_{house.code}.png")

    try:
        # ১. রিপোর্ট ডাউনলোড
        logger.info(f"📥 [{house.name}] রিপোর্ট ডাউনলোড শুরু...")
        await page.goto(REPORT_URL, wait_until="domcontentloaded")
        today_str = date.today().strftime("%Y-%m-%d")
        await page.fill("#StartDate", today_str)
        await page.fill("#EndDate", today_str)

        async with page.expect_download() as download_info:
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        await download.save_as(file_path)

        # ২. এক্সেল ফাইল আপডেট ও স্ক্রিনশট (xlwings হেডলেস সাপোর্ট করে)
        success = update_master_file_and_screenshot(file_path, image_path, config)
        
        if success:
            # ৩. হোয়াটসঅ্যাপে পাঠানো (প্লে-রাইট দিয়ে হেডলেস অটোমেশন) ✅
            await send_wa_headless(page, config['wa_group'], image_path, house.name)

    finally:
        if page: await page.close()
        if os.path.exists(file_path): os.remove(file_path)

def update_master_file_and_screenshot(downloaded_file, image_path, config):
    """xlwings ব্যাকগ্রাউন্ড প্রসেস (স্মার্ট ফাইল লক হ্যান্ডলিং সহ)"""
    master_path = config['master_path']
    file_name = os.path.basename(master_path)
    temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{file_name}")
    
    app = None
    wb = None
    try:
        # ১. চেক করা যে ফাইলটি আগে থেকেই কোনো এক্সেলে খোলা আছে কি না
        # থাকলে xlwings সেটাতে কানেক্ট হয়ে বন্ধ করার চেষ্টা করবে
        try:
            for app_inst in xw.apps:
                for book in app_inst.books:
                    if book.name.lower() == file_name.lower():
                        logger.info(f"📊 {file_name} আগে থেকেই খোলা। এটি বন্ধ করা হচ্ছে...")
                        book.close()
        except: pass

        # ২. ডাটা রিড করা
        data_df = pd.read_excel(downloaded_file)
        
        # ৩. লোকাল কপি তৈরি করার আগে নিশ্চিত হওয়া যে ফাইলটি লকড নয়
        if os.path.exists(temp_path): os.remove(temp_path)
        shutil.copy2(master_path, temp_path)
        
        # ৪. এক্সেল অ্যাপ চালু করা (Headless settings)
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False # ফালতু পপ-আপ বন্ধ করবে
        
        wb = app.books.open(temp_path)
        sheet = wb.sheets[config['master_sheet']]
        
        # ৫. ডাটা রাইট
        sheet.range("A:Y").clear_contents()
        sheet.range("A1").options(pd.DataFrame, index=False).value = data_df
        
        # ৬. স্ক্রিনশট নেওয়া
        wa_sheet = wb.sheets[config['wa_sheet']]
        # স্লাইট বিরতি যাতে ডাটা রেন্ডার হতে পারে
        time.sleep(1)
        wa_sheet.range(config['wa_range']).to_png(image_path)
        
        # ৭. সেভ এবং ক্লোজ লজিক ✅
        wb.save()
        wb.close()
        app.quit()
        
        # ৮. ওএস (Windows) কে ফাইল লক রিলিজ করার জন্য ২ সেকেন্ড সময় দেওয়া
        app = None # অবজেক্ট রিমুভ
        time.sleep(2) 
        
        # ৯. ফাইনাল মুভ (ট্রাই-এক্সেপ্ট সহ যাতে এরর না দেয়)
        try:
            shutil.move(temp_path, master_path)
            logger.info(f"✅ [{file_name}] মাস্টার ফাইল ও স্ক্রিনশট সফল।")
            return True
        except PermissionError:
            logger.error(f"❌ ফাইলটি এখনো লকড! ম্যানুয়ালি এক্সেল বন্ধ করুন।")
            return False

    except Exception as e:
        logger.error(f"❌ Excel Update Error: {str(e)}")
        if wb: wb.close()
        if app: app.quit()
        return False


async def send_wa_headless(page, group_id, image_path, house_name):
    """প্লে-রাইট ব্যবহার করে পুরোপুরি হেডলেস হোয়াটসঅ্যাপ মেসেজ"""
    wa_url = f"https://web.whatsapp.com/accept?code={group_id}"
    try:
        logger.info(f"📱 [{house_name}] হোয়াটসঅ্যাপে পাঠানো হচ্ছে (Headless)...")
        await page.goto(wa_url, wait_until="domcontentloaded")
        
        # ১. চ্যাট বক্স লোড হওয়া পর্যন্ত অপেক্ষা
        # হোয়াটসঅ্যাপ ওয়েব লোড হতে সময় নেয়, তাই একটু বেশি সময় দেওয়া হলো
        await page.wait_for_selector('div[contenteditable="true"]', timeout=60000)
        
        # ২. ইমেজ ফাইলটি ইনপুট এলিমেন্টে সেট করা ✅
        # এটি 'Paste' করার বদলে সরাসরি ফাইল আপলোড করবে যা হেডলেস মুডে কাজ করে
        file_input = await page.query_selector('input[type="file"]')
        await file_input.set_input_files(image_path)
        
        # ৩. ক্যাপশন টাইপ করা
        await asyncio.sleep(2)
        caption = f"GA Live Report ({house_name}): {datetime.now().strftime('%I:%M %p')}"
        await page.keyboard.type(caption)
        
        # ৪. সেন্ড করা
        await page.keyboard.press("Enter")
        await asyncio.sleep(3) # সেন্ডিং নিশ্চিত করতে বাফার
        
        if os.path.exists(image_path): os.remove(image_path)
        logger.info(f"✅ [{house_name}] হোয়াটসঅ্যাপে সফলভাবে পাঠানো হয়েছে।")
    except Exception as e:
        logger.error(f"❌ Headless WA Error: {e}")