import time

class OTPManager:
    def __init__(self):
        self.latest_otp = None
        self.received_at = 0
        self.is_used = True

    def update_otp(self, code: str):
        self.latest_otp = str(code)
        self.received_at = time.time()
        self.is_used = False

    async def wait_for_fresh_otp(self, timeout=120):
        """ওটিপি আসার জন্য ১২০ সেকেন্ড অপেক্ষা করবে"""
        start_wait = time.time()
        print(f"⏳ [OTP] ওটিপি-র জন্য অপেক্ষা করছি (Timeout: {timeout}s)...")
        
        import asyncio
        while time.time() - start_wait < timeout:
            if not self.is_used and self.latest_otp:
                # ওটিপি ২ মিনিটের বেশি পুরনো কি না চেক
                if time.time() - self.received_at < 120:
                    otp = self.latest_otp
                    self.is_used = True # এক ওটিপি একবারই ব্যবহার হবে
                    print(f"✅ [OTP] ওটিপি পাওয়া গেছে: {otp}")
                    return otp
            
            await asyncio.sleep(2)
        
        return None

otp_manager = OTPManager()