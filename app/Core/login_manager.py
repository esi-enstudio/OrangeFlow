import asyncio
import os
import logging
from playwright.async_api import async_playwright
from app.Core.otp_manager import otp_manager

# লগার সেটআপ
logger = logging.getLogger(__name__)
login_lock = asyncio.Lock()

class DMSLoginManager:
    def __init__(self):
        self.login_url = "https://blkdms.banglalink.net/Account/Login"

    async def get_browser_context(self, playwright, session_path: str):
        """সেশন ফাইলসহ ব্রাউজার এবং কন্টেক্সট জেনারেট করার ফাংশন"""
        # ব্যাকগ্রাউন্ডে চলার জন্য headless=True রাখা হয়েছে
        browser = await playwright.chromium.launch(headless=False)
        
        if os.path.exists(session_path):
            logger.info(f"📂 [Context] সেশন ফাইল লোড করা হচ্ছে: {session_path}")
            context = await browser.new_context(storage_state=session_path)
        else:
            context = await browser.new_context()
        
        return browser, context

    
    async def is_session_valid(self, page):
        """সেশন সচল আছে কি না তা নিখুঁতভাবে চেক করার লজিক"""
        try:
            # সরাসরি ইনডেক্স বা ড্যাশবোর্ডে যাওয়ার চেষ্টা
            await page.goto("https://blkdms.banglalink.net/", timeout=25000)
            await asyncio.sleep(5) # রিডাইরেক্ট হওয়ার জন্য পর্যাপ্ত সময়

            # চেক: যদি এখনো ইমেইল বক্স দেখা যায়, তবে সেশন নেই
            if await page.query_selector("#Email") or "login" in page.url.lower():
                return False

            # চেক: ড্যাশবোর্ডের কোনো এলিমেন্ট আছে কি না (যেমন: মেনু বার বা লগআউট বাটন)
            is_dashboard = await page.query_selector(".navbar-nav") or await page.query_selector("#SearchType")
            if is_dashboard:
                return True
            
            return False
        except Exception:
            return False


    async def perform_login(self, page, credentials: dict, session_path: str):
        """ডাইনামিক ড্রপডাউন পপুলেশন এবং সেশন হ্যান্ডলিং করে লগইন"""
        async with login_lock:
            try:
                house_name = credentials['house_name']
                logger.info(f"🚀 [Login] হাউজ: {house_name} এর লগইন শুরু...")
                await page.goto(self.login_url)
                
                await asyncio.sleep(3) # পেজ লোড বাফার
                
                # ১. ক্রেডেনশিয়াল ইনপুট
                logger.info("📝 [Login] ইউজারনেম ও পাসওয়ার্ড ইনপুট দিচ্ছি...")
                await page.fill("#Email", str(credentials['user']))
                await page.fill("#Password", str(credentials['pass']))
                
                # ২. ড্রপডাউনে ডাটা আসার জন্য অপেক্ষা
                house_id = str(credentials['house_id'])
                target_option = f"select#Distributor option[value='{house_id}']"
                logger.info(f"⏳ [Login] ড্রপডাউনে হাউজ আইডি '{house_id}' এর অপেক্ষা...")
                
                try:
                    await page.wait_for_selector(target_option, state="attached", timeout=20000)
                except Exception:
                    logger.error(f"❌ [Error] হাউজ আইডি '{house_id}' ড্রপডাউনে পাওয়া যায়নি।")
                    return False
                
                # ৩. হাউজ সিলেকশন (Select2/jQuery হ্যান্ডলিং)
                await page.evaluate(f"""
                    (id) => {{
                        let select = document.getElementById('Distributor');
                        if (select) {{
                            select.value = id;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            if (window.jQuery) window.jQuery(select).val(id).trigger('change');
                        }}
                    }}
                """, house_id)
                
                await asyncio.sleep(2) 
                await page.click("#btnSubmit")
                
                await asyncio.sleep(4) # ওটিপি পেজ লোডের জন্য সময়

                # ৪. ওটিপি হ্যান্ডেলিং (যদি ওটিপি চায়)
                if await page.query_selector("#OTP"):
                    logger.info(f"⏳ [Login] ওটিপি পেজ ডিটেক্ট হয়েছে।")
                    otp = await otp_manager.wait_for_fresh_otp(house_name)

                    if otp:
                        await page.fill("#OTP", str(otp))
                        await page.click("#submitButton")
                        print(f"🟡 [Login] {house_name}: ওটিপি সাবমিট হয়েছে, রিডাইরেক্টের অপেক্ষা...")
                        
                        await asyncio.sleep(5) # ড্যাশবোর্ড লোড হওয়ার জন্য একটু বেশি সময়
                    else:
                        print(f"❌ [Login Failed] {house_name}: ওটিপি পাওয়া যায়নি (Timeout)।")
                        return False

                # নতুন চেক: নিশ্চিত হওয়া যে আমরা ড্যাশবোর্ডে আছি এবং নেটওয়ার্ক শান্ত হয়েছে
                await page.wait_for_load_state("networkidle")
                
                # ৫. সেশন ভ্যালিডেশন এবং সেভ (ফাইনাল চেক)
                # চেক করছি লগইন বক্স চলে গেছে কি না এবং URL এ 'login' নেই কি না
                if not await page.query_selector("#Email") and "login" not in page.url.lower():
                    # সেশন ডিরেক্টরি নিশ্চিত করা
                    os.makedirs(os.path.dirname(session_path), exist_ok=True)
                    
                    # ৫ সেকেন্ডের একটি বাফার দিন যাতে কুকিগুলো পুরোপুরি রাইট হয়
                    await asyncio.sleep(5)
                    
                    # সেশন ফাইল রাইট করা
                    await page.context.storage_state(path=session_path)
                    print(f"🎊 [Session Saved] {credentials['house_name']} - সেশন ফাইল আপডেট হয়েছে।")

                    return True
                else:
                    print(f"❌ [Login Failed] {house_name} - ৫ সেকেন্ড পরেও লগইন পেজেই আটকে আছে।")
                    return False

            except Exception as e:
                logger.error(f"❌ [Critical Login Error] {str(e)}")
                return False

dms_login = DMSLoginManager()