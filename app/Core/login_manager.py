import asyncio
import os
import time
import logging
from playwright.async_api import Page
from app.Core.otp_manager import otp_manager

# লগিং কনফিগারেশন
logger = logging.getLogger(__name__)

class DMSLoginManager:
    def __init__(self):
        self.login_url = "https://blkdms.banglalink.net/Account/Login"
        self._locks = {}

    def get_lock(self, house_id):
        """নির্দিষ্ট হাউজের জন্য একটি লক রিটার্ন করবে যাতে একই হাউজে ডাবল ওটিপি না যায়"""
        if house_id not in self._locks:
            self._locks[house_id] = asyncio.Lock()
        return self._locks[house_id]

    async def is_session_valid(self, page: Page):
        """সেশন সচল আছে কি না তা চেক করা"""
        try:
            logger.info("🔍 [Session] সেশন ভ্যালিডিটি চেক করা হচ্ছে...")
            await page.goto(
                "https://blkdms.banglalink.net/SmartSearchReport", 
                timeout=40000, 
                wait_until="commit" 
            )
            await asyncio.sleep(3) 

            current_url = page.url.lower()
            if "login" not in current_url:
                if await page.query_selector("#SearchType"):
                    logger.info("✅ [Session] সেশন সচল আছে।")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ [Session Error] চেক করার সময় এরর: {str(e)}")
            return False

    async def perform_login(self, page: Page, credentials: dict):
        """হাউজ ভিত্তিক ডাইনামিক লগইন লজিক (সংশোধিত ওটিপি লজিক)"""
        house_id = str(credentials['house_id'])
        h_code = credentials.get('code')
        
        async with self.get_lock(house_id):
            try:
                logger.info(f"🚀 [Login] লগইন শুরু: {credentials['house_name']} ({h_code})")
                await page.goto(self.login_url)
                await asyncio.sleep(2) 
                
                await page.fill("#Email", str(credentials['user']))
                await page.fill("#Password", str(credentials['pass']))
                
                target_option = f"select#Distributor option[value='{house_id}']"
                try:
                    await page.wait_for_selector(target_option, state="attached", timeout=20000)
                except:
                    logger.error(f"❌ [Error] নির্ধারিত সময়ে ড্রপডাউনে হাউজ {house_id} আসেনি।")
                    return False

                await asyncio.sleep(1) 

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
                
                await asyncio.sleep(1) 
                
                # লগইন ক্লিকে যাওয়ার আগের সময় (OTP ফিল্টারের জন্য)
                login_click_time = time.time()
                await page.click("#btnSubmit")
                
                # ৫. স্মার্ট ওটিপি ডিটেকশন ✅
                otp_box_found = False
                try:
                    # ১০ সেকেন্ড অপেক্ষা করা ওটিপি বক্সের জন্য
                    await page.wait_for_selector("#OTP", state="visible", timeout=12000)
                    otp_box_found = True
                    logger.info(f"⏳ [Login] ওটিপি পেজ ডিটেক্ট হয়েছে। ওটিপি খুঁজছি...")
                except:
                    logger.info("ℹ️ [Login] ওটিপি বক্স পাওয়া যায়নি, সরাসরি ড্যাশবোর্ড চেক করছি...")

                if otp_box_found:
                    # ওটিপি ম্যানেজারের মাধ্যমে ফ্রেশ ওটিপি নেওয়া
                    otp = await otp_manager.wait_for_fresh_otp(
                        target_id=h_code, 
                        request_time=login_click_time
                    )

                    if otp:
                        await page.fill("#OTP", str(otp))
                        await page.click("#submitButton")
                        logger.info(f"🔵 [Login] ওটিপি {otp} দিয়ে সাবমিট করা হয়েছে।")
                        
                        # রিডাইরেক্ট হওয়া পর্যন্ত অপেক্ষা
                        try:
                            await page.wait_for_function(
                                "() => !window.location.href.toLowerCase().includes('login')",
                                timeout=25000
                            )
                        except:
                            logger.warning("⚠️ [Login] রিডাইরেক্ট স্লো হচ্ছে...")
                    else:
                        logger.error(f"❌ [Login] ওটিপি সংগ্রহ টাইমআউট! হাউজ: {h_code}")
                        return False

                # ৬. ফাইনাল ভ্যালিডেশন
                await asyncio.sleep(4) # সেশন সেভ হওয়ার জন্য পর্যাপ্ত সময়
                
                if "login" not in page.url.lower():
                    logger.info(f"✅ [Login] সফল: {credentials['house_name']}")
                    return True
                else:
                    logger.error(f"❌ [Login] ব্যর্থ: এখনো লগইন পেজে রয়ে গেছে।")
                    return False

            except Exception as e:
                logger.error(f"❌ [Critical Login Error] {str(e)}")
                return False

# গ্লোবাল অবজেক্ট
dms_login = DMSLoginManager()