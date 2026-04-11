import os
import asyncio
import logging
from app.Core.automation_engine import engine
from app.Core.login_manager import dms_login

logger = logging.getLogger(__name__)
SESSION_DIR = "sessions"

class SessionManager:
    def __init__(self):
        # প্রতিটি হাউজের জন্য আলাদা লক যাতে ওটিপি কনফ্লিক্ট না হয়
        self._locks = {}
        if not os.path.exists(SESSION_DIR):
            os.makedirs(SESSION_DIR)

    def _get_house_lock(self, house_code):
        if house_code not in self._locks:
            self._locks[house_code] = asyncio.Lock()
        return self._locks[house_code]

    async def get_valid_page(self, credentials: dict):
        """
        জেসন সেশন ফাইল ব্যবহার করে একটি সচল পেজ ও কন্টেক্সট দিবে।
        এটি প্যারালাল প্রসেসিং সাপোর্ট করে।
        """
        h_code = credentials['code']
        session_path = os.path.join(SESSION_DIR, f"session_{h_code}.json")
        lock = self._get_house_lock(h_code)

        # ১. সেশন চেক এবং লগইন প্রসেসটি লকের ভেতর থাকবে
        async with lock:
            browser = await engine.get_browser()
            
            # ২. সেশন ফাইল থাকলে সেটি দিয়ে কন্টেক্সট খোলা
            if os.path.exists(session_path):
                context = await browser.new_context(storage_state=session_path)
                logger.info(f"📂 [Manager] {h_code} সেশন ফাইল লোড করা হয়েছে।")
            else:
                context = await browser.new_context()
                logger.info(f"🆕 [Manager] {h_code} এর কোনো ফাইল নেই, নতুন সেশন লাগবে।")

            page = await context.new_page()

            # ৩. সেশন কি কাজ করছে?
            if await dms_login.is_session_valid(page):
                logger.info(f"✅ [Manager] {h_code} সেশন বর্তমানে সচল।")
                return page, context
            else:
                # ৪. সেশন মৃত হলে লগইন করা (এটি নতুন জেসন সেভ করবে)
                logger.warning(f"⚠️ [Manager] {h_code} সেশন এক্সপায়ার হয়েছে। লগইন শুরু হচ্ছে...")
                
                # লগইন ম্যানেজার এখন সেশন পাথে ডাটা সেভ করবে
                success = await dms_login.perform_login(page, credentials, session_path)
                
                if success:
                    return page, context
                else:
                    await page.close()
                    await context.close()
                    raise Exception(f"DMS Login failed for {h_code} after session expiration.")

session_manager = SessionManager()