import asyncio
import os
import time
import logging
from playwright.async_api import async_playwright
from app.Core.otp_manager import otp_manager

# লগিং কনফিগারেশন
logger = logging.getLogger(__name__)

class DMSLoginManager:
    def __init__(self):
        self.login_url = "https://blkdms.banglalink.net/Account/Login"
        # প্রতিটি হাউজের জন্য আলাদা লক রাখার ডিকশনারি
        self._locks = {}

    def get_lock(self, house_id):
        """নির্দিষ্ট হাউজের জন্য একটি লক রিটার্ন করবে"""
        if house_id not in self._locks:
            self._locks[house_id] = asyncio.Lock()
        return self._locks[house_id]

    async def get_browser_context(self, playwright, session_path: str):
        """সেশন ফাইলসহ ব্রাউজার এবং কন্টেক্সট জেনারেট করার ফাংশন"""
        # ব্রাউজার লঞ্চ (Headless=True প্রডাকশনের জন্য)
        browser = await playwright.chromium.launch(headless=True)
        
        # সেশন ফাইল থাকলে সেটি লোড করবে, না থাকলে ফ্রেশ কন্টেক্সট
        if os.path.exists(session_path):
            context = await browser.new_context(storage_state=session_path)
        else:
            context = await browser.new_context()
        
        return browser, context
    
    async def is_session_valid(self, page):
        """সেশন সচল আছে কি না তা চেক করা"""
        try:
            logger.info("🔍 [Session] Verifying current session validity...")
            
            # সরাসরি স্মার্ট সার্চ রিপোর্টে যাওয়ার চেষ্টা (লগইন থাকলে এটি ওপেন হয়)
            await page.goto("https://blkdms.banglalink.net/SmartSearchReport", timeout=15000)
            await asyncio.sleep(2) # রিডাইরেক্ট বাফার


            # যদি URL-এ 'login' না থাকে এবং সার্চ টাইপ এলিমেন্ট পাওয়া যায়
            if "login" not in page.url.lower() and await page.query_selector("#SearchType"):
                logger.info("✅ [Session] Session is valid. No login needed.")
                return True
            
            logger.warning("⚠️ [Session] Session is invalid or expired.")
            return False
        except Exception as e:
            logger.error(f"❌ [Session Error] ভ্যালিডিটি চেক এরর: {str(e)}")
            return False

    async def perform_login(self, page, credentials: dict, session_path: str):
        """হাউজ ভিত্তিক ডাইনামিক লগইন লজিক"""
        house_id = str(credentials['house_id'])
        
        # শুধুমাত্র এই নির্দিষ্ট হাউজের জন্য লক ব্যবহার করা হচ্ছে
        async with self.get_lock(house_id):
            try:
                logger.info(f"🚀 [Login] লগইন শুরু: {credentials['house_name']} (ID: {house_id})")
                await page.goto(self.login_url)
                await asyncio.sleep(2) 
                
                # ১. ক্রেডেনশিয়াল ইনপুট
                await page.fill("#Email", str(credentials['user']))
                await page.fill("#Password", str(credentials['pass']))
                
                # ২. ড্রপডাউনে ডাটা আসার জন্য অপেক্ষা
                target_option = f"select#Distributor option[value='{house_id}']"
                try:
                    await page.wait_for_selector(target_option, state="attached", timeout=20000)
                except:
                    logger.error(f"❌ [Error] নির্ধারিত সময়ে ড্রপডাউনে হাউজ {house_id} আসেনি।")
                    return False

                await asyncio.sleep(2) 

                # ৩. হাউজ সিলেকশন (JS লজিক)
                await page.evaluate(f"""
                    (function() {{
                        let select = document.getElementById('Distributor');
                        if (select) {{
                            select.value = '{house_id}';
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            if (window.jQuery) {{
                                window.jQuery(select).val('{house_id}').trigger('change');
                            }}
                        }}
                    }})();
                """)
                
                await asyncio.sleep(2) 
                await page.click("#btnSubmit")
                await asyncio.sleep(2)
                
                if await page.query_selector("#OTP"):
                    # হাউজ কোড (MYMVAI01) ব্যবহার করে ওটিপি খুঁজি
                    h_code = credentials.get('code') 
                    
                    if not h_code:
                        logger.error("❌ [Login] এরর: ক্রেডেনশিয়াল ডিকশনারিতে হাউজ 'code' পাওয়া যায়নি!")
                        return False

                    # ওটিপি ম্যানেজারের মাধ্যমে ফ্রেশ ওটিপি-র জন্য ওয়েট করা
                    otp = await otp_manager.wait_for_fresh_otp(target_id=h_code)

                    if otp:
                        await page.fill("#OTP", str(otp))
                        await page.click("#submitButton")
                        logger.info(f"🔵 [Login] ওটিপি {otp} ইনপুট দিয়ে সাবমিট করা হয়েছে।")
                        
                        # রিডাইরেক্ট সম্পন্ন হওয়া পর্যন্ত অপেক্ষা (লগইন ইউআরএল না থাকা পর্যন্ত)
                        try:
                            await page.wait_for_function(
                                "() => !window.location.href.toLowerCase().includes('login')",
                                timeout=20000
                            )
                        except:
                            logger.warning("⚠️ [Login] রিডাইরেক্ট হতে সময় নিচ্ছে...")
                    else:
                        logger.error(f"❌ [Login] ওটিপি সংগ্রহ ব্যর্থ হয়েছে (Timeout) হাউজ: {h_code}")
                        return False

                # ৫. ফাইনাল সেশন ভ্যালিডেশন এবং সেভ
                await asyncio.sleep(2) # ছোট বাফার যাতে পেজ লোড ফিনিশ হয়
                
                if "login" not in page.url.lower():
                    # সেশন ডিরেক্টরি নিশ্চিত করা
                    session_dir = os.path.dirname(session_path)
                    if session_dir and not os.path.exists(session_dir):
                        os.makedirs(session_dir, exist_ok=True)

                    # সেশন স্টেট সেভ করা
                    await page.context.storage_state(path=session_path)
                    logger.info(f"✅ [Login] সফলভাবে লগইন সম্পন্ন: {credentials['house_name']}")
                    return True
                else:
                    logger.error(f"❌ [Login] ব্যর্থ: এখনো লগইন পেজে রয়ে গেছে। (URL: {page.url})")
                    return False

            except Exception as e:
                logger.error(f"❌ [Critical Login Error] {str(e)}")
                return False


# গ্লোবাল অবজেক্ট
dms_login = DMSLoginManager()