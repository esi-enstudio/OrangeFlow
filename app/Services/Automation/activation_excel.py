import pandas as pd
import logging
import os
import asyncio
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func
from app.Models.activation import Activation
from app.Models.retailer import Retailer
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num

logger = logging.getLogger(__name__)

async def process_activation_excel(file_path, house_id, progress_callback):
    """উন্নত বাল্ক প্রসেসিং লজিক (৯,৫০০+ ডাটার জন্য অপ্টিমাইজড) ✅"""
    try:
        # ১. ডাটা লোড (dtype=str ব্যবহার করা হয়েছে যাতে বড় সংখ্যা ঠিক থাকে)
        df = pd.read_excel(file_path, dtype=str)
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
        
        total_rows = len(df)
        if total_rows == 0: return 0, "ফাইলটি খালি।"

        def clean(val):
            v = str(val).strip()
            # Excel এ leading single quote থাকলে তা সরানো
            if v.startswith("'"):
                v = v[1:]
            v = v.replace("'", "")
            if v == "" or v.lower() in ["nan", "none", "null"]:
                return None

            # তারিখ থেকে সময় বাদ দেওয়া
            if ' ' in v and '-' in v:
                v = v.split(' ')[0]  # "2026-04-21 00:00:00" -> "2026-04-21"

            return v if v else None

        async with async_session() as session:
            # ২. পারফরম্যান্স বুস্ট: সব রিটেইলারকে মেমরিতে নিয়ে আসা ✅
            # এতে ৯,৫০০ বার আলাদা করে ডাটাবেজে সার্চ করতে হবে না
            logger.info(f"⏳ হাউজ {house_id} এর রিটেইলার ম্যাপ তৈরি হচ্ছে...")
            ret_res = await session.execute(
                select(Retailer.retailer_code, Retailer.id).where(Retailer.house_id == house_id)
            )
            retailer_map = {r.retailer_code: r.id for r in ret_res.all()}

            count = 0
            # ৩. ডাটা প্রসেসিং লুপ
            for index, row in df.iterrows():
                sim_no = clean(row.get('SIM_NO'))
                if not sim_no: continue
                
                r_code = clean(row.get('RETAILER_CODE'))
                # ডাটাবেজ হিটের বদলে মেমরি ম্যাপ থেকে আইডি নেওয়া (অত্যন্ত দ্রুত) ✅
                target_retailer_id = retailer_map.get(r_code) if r_code else None

                # তারিখ প্রসেসিং
                try:
                    act_date = pd.to_datetime(row.get('ACTIVATION_DATE')).date()
                except:
                    act_date = None

                # ডাটা ম্যাপ (সকল কলাম)
                data_map = {
                    "house_id": house_id,
                    "retailer_id": target_retailer_id,
                    "sim_no": sim_no,
                    "activation_date": act_date,
                    "activation_time": clean(row.get('ACTIVATION_TIME')),
                    "retailer_code": r_code,
                    "retailer_name": clean(row.get('RETAILER_NAME')),
                    "bts_code": clean(row.get('BTS_CODE')),
                    "thana": clean(row.get('THANA')),
                    "promotion": clean(row.get('PROMOTION')),
                    "product_code": clean(row.get('PRODUCT_CODE')),
                    "product_name": clean(row.get('PRODUCT_NAME')),
                    "msisdn": clean(row.get('MSISDN')),
                    "selling_price": clean(row.get('SELLING_PRICE')),
                    "bp_flag": clean(row.get('BP_FLAG')),
                    "bp_number": clean(row.get('BP_NUMBER')),
                    "fc_bts_code": clean(row.get('FC_BTS_CODE')),
                    "bio_bts_code": clean(row.get('BIO_BTS_CODE')),
                    "dh_lifting_date": clean(row.get('DH_LIFTINGDATE')),
                    "issue_date": clean(row.get('ISSUEDATE')),
                    "subscription_type": clean(row.get('SUBSCRIPTION_TYPE')),
                    "service_class": clean(row.get('SERVICE_CLASS')),
                    "customer_second_contact": clean(row.get('CUSTOMER_SECOND_CONTACT')),
                    "updated_at": func.now()
                }

                # ৪. PostgreSQL Upsert
                stmt = insert(Activation).values(**data_map)
                update_cols = {k: v for k, v in data_map.items() if k not in ['sim_no', 'house_id']}
                
                stmt = stmt.on_conflict_do_update(
                    index_elements=['sim_no'],
                    set_=update_cols
                )
                
                await session.execute(stmt)
                count += 1

                # ৫. টেলিগ্রাম প্রগ্রেস আপডেট (থ্রোটলিং করা হয়েছে) ⚠️
                # বড় ফাইলের জন্য প্রতি ২০০টিতে একবার আপডেট দিলে টেলিগ্রাম ব্লক করবে না
                if count % 200 == 0 or count == total_rows:
                    percent = round((count / total_rows) * 100)
                    await progress_callback(
                        f"📊 <b>এক্টিভেশন আপলোড প্রগ্রেস:</b> {bn_num(percent)}%\n"
                        f"📈 প্রসেস হয়েছে: <code>{bn_num(count)}</code> / <code>{bn_num(total_rows)}</code>"
                    )
            
            # সব শেষে একবারই ডাটাবেজে পার্মানেন্ট সেভ হবে ✅
            await session.commit()
            return count, None

    except Exception as e:
        logger.error(f"❌ Critical Sync Error: {str(e)}")
        return 0, f"{str(e)}"