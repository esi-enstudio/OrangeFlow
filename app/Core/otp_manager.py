import time
import asyncio
import logging

logger = logging.getLogger(__name__)

class OTPManager:
    def __init__(self):
        # ওটিপিগুলোর একটি তালিকা রাখা হবে
        # প্রতিটি আইটেম: {"code": "123456", "received_at": timestamp, "is_used": False}
        self.otp_pool = []

    def update_otp(self, code: str, house_identifier: str):
        """ম্যাক্রোড্রয়েড থেকে ওটিপি আসলে এই পুলে যোগ হবে"""
        new_otp = {
            "code": str(code),
            "identifier": str(house_identifier).strip().upper(), # বড় হাতের করে সেভ
            "received_at": time.time(),
            "is_used": False
        }
        self.otp_pool.append(new_otp)
        logger.info(f"🆕 [OTP Pool] New OTP added: {code}. Total in pool: {len(self.otp_pool)}")
        
        # পুরনো ওটিপি (৫ মিনিটের বেশি) পরিষ্কার করা যাতে মেমোরি নষ্ট না হয়
        self._cleanup_old_otps()

    async def wait_for_fresh_otp(self, target_id: str, timeout=110):
        """
        ওটিপি-র জন্য অপেক্ষা করবে। 
        হাউজ আইডি/কোড দিয়ে ওটিপি খুঁজে বের করবে
        """
        start_wait = time.time()
        target_id = str(target_id).strip().upper()
        
        logger.info(f"⏳ [OTP] {target_id} এর ওটিপি খুঁজছি...")
        
        while time.time() - start_wait < timeout:
            # পুলের সব ওটিপি চেক করা
            for otp_data in self.otp_pool:
                # লজিক: হাউজের নাম মিলতে হবে এবং ২ মিনিটের বেশি পুরনো হওয়া যাবে না
                if not otp_data["is_used"] and \
                    otp_data["identifier"] == target_id  and \
                   (time.time() - otp_data["received_at"] < 120):

                    otp_code = otp_data["code"]
                    otp_data["is_used"] = True # এটি ব্যবহৃত হিসেবে মার্ক করা হলো
                    
                    logger.info(f"✅ [OTP] {target_id} এর জন্য কোড পাওয়া গেছে: {otp_code}")

                    return otp_code
            
            await asyncio.sleep(1) # ২ সেকেন্ড পর পর চেক করবে
        
        logger.error("❌ [OTP] ওটিপি পাওয়ার সময় শেষ (Timeout)।")
        return None

    def _cleanup_old_otps(self):
        """৫ মিনিটের বেশি পুরনো ওটিপিগুলো লিস্ট থেকে মুছে ফেলবে"""
        current_time = time.time()
        self.otp_pool = [otp for otp in self.otp_pool if current_time - otp["received_at"] < 300]

# গ্লোবাল অবজেক্ট
otp_manager = OTPManager()