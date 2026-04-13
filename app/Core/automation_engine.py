import asyncio
import logging
from playwright.async_api import async_playwright
from config import settings

logger = logging.getLogger(__name__)

class AutomationEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            # সাধারণ ব্রাউজার লঞ্চ
            self.browser = await self.playwright.chromium.launch(
                headless=settings.HEADLESS,
                args=['--disable-blink-features=AutomationControlled']
            )
            logger.info("🚀 [Engine] Browser Engine Started.")

    async def get_browser(self):
        """ব্রাউজার অবজেক্ট রিটার্ন করবে, বন্ধ থাকলে চালু করবে"""
        if not self.browser or not self.playwright:
            await self.start()
        return self.browser


    async def stop(self):
        """বট বন্ধের সময় ব্রাউজার এবং প্লে-রাইট ক্লিনলি বন্ধ করবে"""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                
            logger.info("✅ [Engine] Browser Engine and Playwright Stopped.")
        except Exception as e:
            logger.error(f"⚠️ [Engine] Error during engine stop: {e}")


# গ্লোবাল ইঞ্জিন ইনস্ট্যান্স
engine = AutomationEngine()