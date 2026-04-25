import os
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from app.Core.automation_engine import engine
from app.Core.login_manager import dms_login
from app.Services.db_service import async_session
from app.Models.house import House

logger = logging.getLogger(__name__)
SESSION_DIR = "sessions"

class SessionManager:
    def __init__(self):
        self._locks = {}
        if not os.path.exists(SESSION_DIR):
            os.makedirs(SESSION_DIR, exist_ok=True)

    def _get_house_lock(self, house_code):
        if house_code not in self._locks:
            self._locks[house_code] = asyncio.Lock()
        return self._locks[house_code]

    async def get_valid_page(self, credentials: dict):
        """
        হাউজের সাবস্ক্রিপশন চেক এবং ডিএমএস সেশন ভ্যালিডেশন করে একটি সচল পেজ দিবে।
        """

        h_code = credentials['code']
        session_path = os.path.join(SESSION_DIR, f"session_{h_code}.json")
        lock = self._get_house_lock(h_code)
        
        # বর্তমান তারিখ (শুধু Date অংশ)
        today = datetime.now().date()

        # ১. ডাটাবেজ চেক (Strict Security) ✅
        async with async_session() as session:
            res = await session.execute(select(House).where(House.code == h_code))
            house_db = res.scalar_one_or_none()

            if not house_db:
                raise Exception(f"হাউজ {h_code} ডাটাবেজে পাওয়া যায়নি।")
            
            # মেয়াদ ডিবাগ করার জন্য প্রিন্ট লজিক
            expiry_date = house_db.subscription_date.date() if house_db.subscription_date else None
            logger.info(f"📊 [Check] হাউজ: {house_db.name} | মেয়াদ শেষ: {expiry_date} | আজ: {today}")

            # স্ট্যাটাস চেক
            if not house_db.is_active:
                raise Exception(f"হাউজ {house_db.name} বর্তমানে ইন-একটিভ আছে।")
            
            # সাবস্ক্রিপশন চেক (যদি তারিখ না থাকে তবে আমরা ডিফল্টভাবে ব্লক করবো) ✅
            if not expiry_date or expiry_date < today:
                raise Exception(f"হাউজ {house_db.name} এর সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে। (মেয়াদ ছিল: {expiry_date})")

        # ২. সেশন প্রসেস (লকিং)
        async with lock:
            browser = await engine.get_browser()
            
            if os.path.exists(session_path):
                context = await browser.new_context(storage_state=session_path)
                logger.info(f"📂 [Manager] {h_code} সেশন ফাইল লোড করা হয়েছে।")
            else:
                context = await browser.new_context()
                logger.info(f"🆕 [Manager] {h_code} নতুন সেশন তৈরি হবে।")

            page = await context.new_page()

            # ডিএমএস সেশন চেক
            if await dms_login.is_session_valid(page):
                logger.info(f"✅ [Manager] {h_code} ডিএমএস সেশন সচল আছে।")
                return page, context
            else:
                logger.warning(f"⚠️ [Manager] {h_code} সেশন নেই। অটো-লগইন শুরু...")
                success = await dms_login.perform_login(page, credentials, session_path)
                
                if success:
                    return page, context
                else:
                    await page.close()
                    await context.close()
                    raise Exception(f"DMS Login failed for {h_code}.")

session_manager = SessionManager()