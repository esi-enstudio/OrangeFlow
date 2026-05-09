import pandas as pd
import logging
from sqlalchemy import select, delete
from app.Models.mela import MelaEligibleBTS 
from app.Models.bts import BTS
from app.Services.db_service import async_session

logger = logging.getLogger(__name__)

async def process_eligible_bts_excel(file_path, house_id, progress_callback):
    """এক্সেল থেকে বিটিএস কোড নিয়ে এলিজিবল লিস্ট তৈরি করা"""
    try:
        df = pd.read_excel(file_path, dtype=str)
        # হেডারের স্পেস রিমুভ ও আপারকেস করা
        df.columns = [c.strip().upper() for c in df.columns]
        
        if 'BTS CODE' not in df.columns:
            return 0, "এক্সেলে 'BTS CODE' নামে কোনো কলাম পাওয়া যায়নি।"

        total = len(df)
        async with async_session() as session:
            # ওই হাউজের আগের সকল এলিজিবল লিস্ট মুছে ফেলা (ফ্রেশ আপলোডের জন্য)
            await session.execute(delete(MelaEligibleBTS ).where(MelaEligibleBTS .house_id == house_id))
            
            count = 0
            for index, row in df.iterrows():
                bts_code = str(row['BTS CODE']).strip().upper()
                
                # bts_list টেবিল থেকে আইডি খুঁজে বের করা ✅
                res = await session.execute(select(BTS.id).where(BTS.bts_code == bts_code))
                bts_id = res.scalar_one_or_none()

                if bts_id:
                    session.add(MelaEligibleBTS (house_id=house_id, bts_id=bts_id))
                    count += 1
                
                # প্রগ্রেস আপডেট
                if (index + 1) % 10 == 0 or (index + 1) == total:
                    await progress_callback(f"⏳ প্রসেসিং: {round(((index+1)/total)*100)}% ({index+1}/{total})")
            
            await session.commit()
            return count, None
    except Exception as e:
        logger.error(f"Eligible BTS Upload Error: {e}")
        return 0, str(e)