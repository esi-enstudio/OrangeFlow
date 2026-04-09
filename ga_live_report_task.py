import asyncio
import os
import shutil
import time
import warnings
import pandas as pd
import xlwings as xw
import pyautogui
import pywhatkit as kit
import webbrowser
import win32clipboard # ক্লিপবোর্ডে ইমেজ কপি করার জন্য ✅
from datetime import date, datetime
from playwright.async_api import async_playwright
from colorama import init, Fore
from io import BytesIO
from PIL import Image

# openpyxl এর Stylesheet ওয়ার্নিং বন্ধ করা
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl") # ✅

# আপনার প্রজেক্টের কোর মডিউল ইম্পোর্ট
from app.Core.login_manager import dms_login

init(autoreset=True)

# --- কনফিগারেশন ---
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
REPORT_URL = "https://blkdms.banglalink.net/ActivationReport"
run_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads", f"GA_Live_Report_{run_timestamp}")

# হাউজ লিস্ট (আপনার দেওয়া ডাটা অনুযায়ী)
houses_data = [
    {
        "name": "MYMVAI01", 
        "user": "spatwary", 
        "pass": "Patwary607080@#", 
        "house_id": "125", 
        "code": "MYMVAI01",
        "master_path": r"G:\My Drive\BL\RSO\UC\2026\04_UC_April'26.xlsb",
        "master_sheet": "Activations Live Raw",
        "wa_group": "GuagYPexjY0IM3YdUSyBi2",
        "wa_sheet": "RS0 GA Live",
        "wa_range": "A1:L31"
    },
    {
        "name": "MYMVAI02", 
        "user": "smadina1", 
        "pass": "Modi@1234567890", 
        "house_id": "621", 
        "code": "MYMVAI02",
        "master_path": r"G:\My Drive\BL\RSO\UC\2026\04_UC_April'26 - MYMVAI02.xlsb",
        "master_sheet": "Activations Live Raw",
        "wa_group": "CD9KgPa9JxN21rgGDKBF2J", 
        "wa_sheet": "RS0 GA Live",
        "wa_range": "A1:J16"
    }
]

async def download_report(playwright, house):
    house_name = house['name']
    session_file = os.path.join(SESSION_DIR, f"session_{house['user']}.json")
    browser = await playwright.chromium.launch(headless=False) # দেখার জন্য False রাখা হয়েছে
    
    if os.path.exists(session_file):
        context = await browser.new_context(storage_state=session_file)
    else:
        context = await browser.new_context()
        
    page = await context.new_page()
    
    try:
        print(Fore.YELLOW + f"\n--- {house_name} এর প্রসেস শুরু ---")
        if not await dms_login.is_session_valid(page):
            print(Fore.CYAN + "সেশন ইনভ্যালিড, লগইন করা হচ্ছে...")
            if not await dms_login.perform_login(page, house, session_file):
                return None

        await page.goto(REPORT_URL)
        await page.wait_for_selector("#StartDate")
        
        today_str = date.today().strftime("%Y-%m-%d")
        await page.evaluate(f"document.getElementById('StartDate').value = '{today_str}';")
        await page.evaluate(f"document.getElementById('EndDate').value = '{today_str}';")
        
        if not os.path.exists(DOWNLOAD_PATH):
            os.makedirs(DOWNLOAD_PATH)

        async with page.expect_download() as download_info:
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        save_file_path = os.path.join(DOWNLOAD_PATH, f"{house_name}_{today_str}.xlsx")
        await download.save_as(save_file_path)
        print(Fore.GREEN + f"ডাউনলোড সম্পন্ন: {house_name}")
        return save_file_path
    except Exception as e:
        print(Fore.RED + f"এরর: {str(e)}")
        return None
    finally:
        await browser.close()

def process_single_file(file_path):
    """ডাটা ফিল্টার করা (Swap SIM বাদ দেওয়া)"""
    df = pd.read_excel(file_path)
    if 'PRODUCT_CODE' in df.columns:
        exclude = ['EV-SWAP', 'SIMSWAP', 'ESIMSWAP']
        df = df[~df['PRODUCT_CODE'].isin(exclude)]
    
    new_path = file_path.replace(".xlsx", "_cleaned.xlsx")
    df.to_excel(new_path, index=False)
    return new_path

def update_master_file_and_screenshot(downloaded_file, house_config, is_first=False):
    """লোকাল ফাইলে আপডেট করবে এবং xlwings ব্যবহার করে ব্যাকগ্রাউন্ডে স্ক্রিনশট নিবে।"""
    house_name = house_config['name']
    master_path = house_config['master_path']
    sheet_name = house_config['master_sheet']
    wa_sheet_name = house_config['wa_sheet'] # হোয়াটসঅ্যাপের জন্য আলাদা শিট
    wa_range = house_config['wa_range']
    
    print(Fore.YELLOW + f"📦 {house_name} প্রসেস শুরু হচ্ছে...")
    file_name = os.path.basename(master_path)
    local_temp_path = os.path.join(DOWNLOAD_PATH, f"temp_{house_name}_{file_name}")
    image_path = os.path.join(DOWNLOAD_PATH, f"ss_{house_name}.png")
    
    app = None
    try:
        data_df = pd.read_excel(downloaded_file)
        
        # ১. ফাইল খোলা থাকলে বন্ধ করা
        for app_inst in xw.apps:
            for book in app_inst.books:
                if book.name.lower() == file_name.lower():
                    print(Fore.CYAN + f"📊 {file_name} খোলা আছে। এটি বন্ধ করা হচ্ছে...")
                    book.close()

        # ২. লোকাল কপি তৈরি
        shutil.copy2(master_path, local_temp_path)
        
        # ৩. ডাটা আপডেট এবং স্ক্রিনশট (একই অ্যাপ সেশনে)
        app = xw.App(visible=False, add_book=False)
        wb = app.books.open(local_temp_path)
        
        # --- ডাটা রাইটিং ---
        raw_sheet = wb.sheets[sheet_name]
        raw_sheet.range("A:Y").clear_contents()
        raw_sheet.range("A1").options(pd.DataFrame, index=False).value = data_df
        print(Fore.GREEN + f"✅ {house_name} ডাটা রাইট সম্পন্ন।")

        # --- স্ক্রিনশট নেওয়া (xlwings এর আধুনিক পদ্ধতি) ---
        print(Fore.CYAN + f"📸 {house_name} এর স্ক্রিনশট নেওয়া হচ্ছে...")
        wa_sheet = wb.sheets[wa_sheet_name]
        
        # রেঞ্জটি ইমেজে কনভার্ট করা (এটি ব্যাকগ্রাউন্ডেই কাজ করবে)
        # নিশ্চিত করুন আপনার পিসিতে Pillow (PIL) ইনস্টল আছে
        wa_sheet.range(wa_range).to_png(image_path)
        
        wb.save()
        wb.close()
        app.quit()
        print(Fore.GREEN + "✅ স্ক্রিনশট ফাইল সেভ হয়েছে।")

        # ৪. ফাইলটি গুগল ড্রাইভে ফেরত পাঠানো
        time.sleep(2)
        shutil.move(local_temp_path, master_path)
        print(Fore.GREEN + f"🔄 {house_name} মাস্টার ফাইল সিঙ্ক হয়েছে।")

        # ৫. হোয়াটসঅ্যাপে পাঠানো
        send_whatsapp_only(house_config, image_path, is_first_house=is_first)
        
        return True
    except Exception as e:
        print(Fore.RED + f"❌ {house_name} এরর: {e}")
        if app:
            app.quit()
        return False

def copy_image_to_clipboard(image_path):
    """ইমেজ ফাইলকে উইন্ডোজ ক্লিপবোর্ডে কপি করার ফাংশন"""
    image = Image.open(image_path)
    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def send_whatsapp_only(house_config, image_path, is_first_house=False):
    """একই ব্রাউজার উইন্ডোতে গ্রুপ চেঞ্জ করে ইমেজ পাঠাবে"""
    house_name = house_config['name']
    group_id = house_config['wa_group']
    group_link = f"https://web.whatsapp.com/accept?code={group_id}"

    print(Fore.YELLOW + f"📱 {house_name} এর রিপোর্ট একই উইন্ডোতে পাঠানো হচ্ছে...")
    
    try:
        # ১. ক্লিপবোর্ডে ইমেজ কপি করা
        copy_image_to_clipboard(image_path)

        # ২. ব্রাউজারে গ্রুপ ইউআরএল ওপেন করা
        if is_first_house:
            # প্রথম হাউজের জন্য নতুন করে ব্রাউজার খুলবে
            webbrowser.open(group_link)
            print(Fore.CYAN + "⏳ হোয়াটসঅ্যাপ ওয়েব লোড হওয়ার জন্য অপেক্ষা করছি (৩০ সেকেন্ড)...")
            time.sleep(30) # প্রথমবার লগইন/লোড হওয়ার জন্য বেশি সময়
        else:
            # পরের হাউজগুলোর জন্য একই ট্যাবে অ্যাড্রেস বার ব্যবহার করবে
            pyautogui.hotkey('ctrl', 'l') # অ্যাড্রেস বার ফোকাস (Windows)
            time.sleep(1)
            pyautogui.write(group_link)
            pyautogui.press('enter')
            print(Fore.CYAN + "⏳ গ্রুপ পরিবর্তনের অপেক্ষা করছি (১৫ সেকেন্ড)...")
            time.sleep(15)

        # ৩. ইমেজ পেস্ট এবং সেন্ড
        caption = f"GA Live Report: {datetime.now().strftime('%I:%M %p')}"
        
        # পেস্ট করা (Ctrl+V)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3) # ইমেজ প্রিভিউ আসার জন্য সময়
        
        # ক্যাপশন টাইপ করা (যদি দরকার হয় সরাসরি এন্টার দিলেও হবে)
        pyautogui.write(caption)
        time.sleep(1)
        
        # সেন্ড করার জন্য এন্টার
        pyautogui.press('enter')
        print(Fore.GREEN + f"✅ {house_name} এর রিপোর্ট পাঠানো হয়েছে।")

        # কাজ শেষে লোকাল ইমেজ ডিলিট
        if os.path.exists(image_path): os.remove(image_path)

    except Exception as e:
        print(Fore.RED + f"❌ {house_name} WhatsApp Error: {e}")

async def main():
    async with async_playwright() as p:
        for index, house in enumerate(houses_data):
            file = await download_report(p, house)

            if file:
                cleaned_file = process_single_file(file)
                
                # স্ক্রিনশট নিবে এবং হোয়াটসঅ্যাপে পাঠাবে
                # এখানে index == 0 পাঠালে সে প্রথম হাউজ হিসেবে বেশি ওয়েট করবে
                update_master_file_and_screenshot(cleaned_file, house, is_first=(index == 0))
                
                await asyncio.sleep(5)
        
        print(Fore.GREEN + "\n🎊 সকল হাউজের সকল টাস্ক সফলভাবে সম্পন্ন হয়েছে।")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "\nইউজার দ্বারা কাজ বন্ধ করা হয়েছে।")
