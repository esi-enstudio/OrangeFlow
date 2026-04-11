import asyncio
import os
import shutil
import time
import warnings
import pandas as pd
import xlwings as xw
import pyautogui
import webbrowser
import win32clipboard 
from datetime import date, datetime
from playwright.async_api import async_playwright
from colorama import init, Fore
from io import BytesIO
from PIL import Image

# --- আপনার প্রোজেক্টের কোর মডিউল ইম্পোর্ট ---
from app.Core.automation_engine import engine
from app.Core.session_manager import session_manager

# openpyxl এর Stylesheet ওয়ার্নিং বন্ধ করা
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

init(autoreset=True)

# --- কনফিগারেশন ---
REPORT_URL = "https://blkdms.banglalink.net/ActivationReport"
run_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads", f"GA_Live_Report_{run_timestamp}")

# হাউজ লিস্ট
houses_data = [
    {
        "name": "Patwary Telecom", 
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
        "name": "M/s Modina Store", 
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

async def download_report(house):
    """বর্তমান প্রোজেক্টের সেশন ম্যানেজার ব্যবহার করে রিপোর্ট ডাউনলোড"""
    house_name = house['name']
    
    # আপনার প্রোজেক্টের ফরম্যাট অনুযায়ী ক্রেডেনশিয়াল তৈরি
    credentials = {
        "user": house["user"],
        "pass": house["pass"],
        "house_id": house["house_id"],
        "house_name": house["name"],
        "code": house["code"]
    }

    print(Fore.YELLOW + f"\n--- {house_name} এর প্রসেস শুরু ---")
    
    # ১. সেশন ম্যানেজার থেকে সচল পেজ সংগ্রহ (এটি অটো-লগইন এবং প্রোফাইল হ্যান্ডেল করবে) ✅
    try:
        page, context = await session_manager.get_valid_page(credentials)
    except Exception as e:
        print(Fore.RED + f"❌ সেশন তৈরি করা সম্ভব হয়নি: {e}")
        return None
    
    try:
        # ২. রিপোর্ট পেজে যাওয়া (domcontentloaded দ্রুত এবং স্ট্যাবল)
        await page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#StartDate", timeout=30000)
        
        today_str = date.today().strftime("%Y-%m-%d")
        # সরাসরি টাইপ করার বদলে evaluate ব্যবহার করা নিরাপদ
        await page.evaluate(f"document.getElementById('StartDate').value = '{today_str}';")
        await page.evaluate(f"document.getElementById('EndDate').value = '{today_str}';")
        
        if not os.path.exists(DOWNLOAD_PATH):
            os.makedirs(DOWNLOAD_PATH)

        async with page.expect_download() as download_info:
            await page.click("button:has-text('Export Details')")
        
        download = await download_info.value
        save_file_path = os.path.join(DOWNLOAD_PATH, f"{house_name}_{today_str}.xlsx")
        await download.save_as(save_file_path)
        print(Fore.GREEN + f"✅ ডাউনলোড সম্পন্ন: {house_name}")
        return save_file_path

    except Exception as e:
        print(Fore.RED + f"❌ ডাউনলোড এরর: {str(e)}")
        return None
    finally:
        # ৩. কাজ শেষে শুধু ট্যাব বন্ধ করা (প্রোফাইল সচল থাকবে) ✅
        await page.close()

def process_single_file(file_path):
    """ডাটা ফিল্টার করা (অপরিবর্তিত)"""
    df = pd.read_excel(file_path)
    if 'PRODUCT_CODE' in df.columns:
        exclude = ['EV-SWAP', 'SIMSWAP', 'ESIMSWAP']
        df = df[~df['PRODUCT_CODE'].isin(exclude)]
    
    new_path = file_path.replace(".xlsx", "_cleaned.xlsx")
    df.to_excel(new_path, index=False)
    return new_path

def update_master_file_and_screenshot(downloaded_file, house_config, is_first=False):
    """মাস্টার ফাইল আপডেট ও স্ক্রিনশট (অপরিবর্তিত)"""
    house_name = house_config['name']
    master_path = house_config['master_path']
    sheet_name = house_config['master_sheet']
    wa_sheet_name = house_config['wa_sheet']
    wa_range = house_config['wa_range']
    
    print(Fore.YELLOW + f"📦 {house_name} মাস্টার ফাইল প্রসেস শুরু হচ্ছে...")
    file_name = os.path.basename(master_path)
    local_temp_path = os.path.join(DOWNLOAD_PATH, f"temp_{house_name}_{file_name}")
    image_path = os.path.join(DOWNLOAD_PATH, f"ss_{house_name}.png")
    
    app = None
    try:
        data_df = pd.read_excel(downloaded_file)
        
        for app_inst in xw.apps:
            for book in app_inst.books:
                if book.name.lower() == file_name.lower():
                    book.close()

        shutil.copy2(master_path, local_temp_path)
        
        app = xw.App(visible=False, add_book=False)
        wb = app.books.open(local_temp_path)
        
        raw_sheet = wb.sheets[sheet_name]
        raw_sheet.range("A:Y").clear_contents()
        raw_sheet.range("A1").options(pd.DataFrame, index=False).value = data_df

        wa_sheet = wb.sheets[wa_sheet_name]
        wa_sheet.range(wa_range).to_png(image_path)
        
        wb.save()
        wb.close()
        app.quit()

        time.sleep(2)
        shutil.move(local_temp_path, master_path)
        print(Fore.GREEN + f"🔄 {house_name} মাস্টার ফাইল সিঙ্ক সম্পন্ন।")

        send_whatsapp_only(house_config, image_path, is_first_house=is_first)
        return True
    except Exception as e:
        print(Fore.RED + f"❌ {house_name} এক্সেল এরর: {e}")
        if app: app.quit()
        return False

def copy_image_to_clipboard(image_path):
    """ইমেজ কপি লজিক (অপরিবর্তিত)"""
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
    """হোয়াটসঅ্যাপ মেসেজিং (অপরিবর্তিত)"""
    house_name = house_config['name']
    group_id = house_config['wa_group']
    group_link = f"https://web.whatsapp.com/accept?code={group_id}"

    try:
        copy_image_to_clipboard(image_path)
        if is_first_house:
            webbrowser.open(group_link)
            time.sleep(30)
        else:
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(1)
            pyautogui.write(group_link)
            pyautogui.press('enter')
            time.sleep(15)

        caption = f"GA Live Report: {datetime.now().strftime('%I:%M %p')}"
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)
        pyautogui.write(caption)
        time.sleep(1)
        pyautogui.press('enter')
        print(Fore.GREEN + f"✅ {house_name} হোয়াটসঅ্যাপ রিপোর্ট পাঠানো হয়েছে।")

        if os.path.exists(image_path): os.remove(image_path)
    except Exception as e:
        print(Fore.RED + f"❌ {house_name} WhatsApp Error: {e}")

async def main():
    # ২. প্রোজেক্টের গ্লোবাল ইঞ্জিন স্টার্ট করা ✅
    await engine.start()
    
    try:
        for index, house in enumerate(houses_data):
            # ডাউনলোড ফাংশনে এখন আর p বা playwright প্যারামিটার দরকার নেই
            file = await download_report(house)

            if file:
                cleaned_file = process_single_file(file)
                update_master_file_and_screenshot(cleaned_file, house, is_first=(index == 0))
                await asyncio.sleep(5)
        
        print(Fore.GREEN + "\n🎊 সকল হাউজের কাজ সফলভাবে সম্পন্ন হয়েছে।")
    finally:
        # ৩. কাজ শেষে ইঞ্জিন বন্ধ করা ✅
        await engine.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "\nইউজার দ্বারা কাজ বন্ধ করা হয়েছে।")