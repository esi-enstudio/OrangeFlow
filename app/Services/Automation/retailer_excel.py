import pandas as pd
import os
import asyncio
import logging
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from app.Models.retailer import Retailer
from app.Models.field_force import FieldForce # অটো-লিঙ্কিং এর জন্য জরুরি ✅
from app.Services.db_service import async_session
from app.Utils.helpers import bn_num

logger = logging.getLogger(__name__)

# এক্সেল হেডার এবং ডাটাবেজ কলামের ম্যাপিং
COLUMN_MAP = {
    'RETAILER_CODE': 'retailer_code',
    'RETAILER_NAME': 'name',
    'RETAILER_TYPE': 'type',
    'ENABLED': 'enabled',
    'SIM_SELLER': 'sim_seller',
    'TRANMOBILENO': 'tran_mobile_no',
    'I_TOP_UP_SR_NUMBER': 'itop_sr_number',
    'I_TOP_UP_NUMBER': 'itop_number',
    'SERVICE_POINT': 'service_point',
    'CATEGORY': 'category',
    'OWNER_NAME': 'owner_name',
    'CONTACT_NO': 'contact_no',
    'DISTRICT': 'district',
    'THANA': 'thana',
    'ADDRESS': 'address',
    'NID': 'nid',
    'BP_CODE': 'bp_code',
    'BP_NUMBER': 'bp_number',
    'DOB': 'dob',
    'ROUTE': 'route'
}

async def process_retailer_excel(file_path, house_id, progress_callback=None):
    """রিটেইলার এক্সেল প্রসেস এবং আইটপ নাম্বারের ভিত্তিতে আরএসও লিঙ্কিং লজিক"""
    try:
        # ১. এক্সেল ফাইল রিড করা
        df = pd.read_excel(file_path, dtype=str)
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
        
        total_rows = len(df)
        if total_rows == 0:
            return 0, "ফাইলটিতে কোনো ডাটা পাওয়া যায়নি।"

        # ডাটা ক্লিনিং হেল্পার
        def clean(val):
            v = str(val).strip().replace("'", "") # সিঙ্গেল কোট রিমুভ ✅
            if v == "" or v.lower() in ["nan", "none", "null", "0"]:
                return None
            return v

        async with async_session() as session:
            count = 0
            for index, row in df.iterrows():
                r_code = clean(row.get('RETAILER_CODE'))
                if not r_code:
                    continue

                # ২. আইটপ নাম্বারের ভিত্তিতে আরএসও খুঁজে বের করা ✅
                # রিটেইলার ফাইলের 'I_TOP_UP_SR_NUMBER' এর সাথে ফিল্ড ফোর্সের 'itop_number' ম্যাচ করা হবে
                itop_sr_no = clean(row.get('I_TOP_UP_SR_NUMBER'))
                linked_ff_id = None

                if itop_sr_no:
                    ff_res = await session.execute(
                        select(FieldForce.id).where(
                            FieldForce.itop_number == itop_sr_no,
                            FieldForce.house_id == house_id
                        )
                    )
                    linked_ff_id = ff_res.scalar_one_or_none()

                # ৩. ইনসার্ট ডাটা ডিকশনারি তৈরি
                values_to_insert = {
                    "house_id": house_id,
                    "field_force_id": linked_ff_id
                }
                
                for excel_header, db_col in COLUMN_MAP.items():
                    values_to_insert[db_col] = clean(row.get(excel_header))

                # ৪. PostgreSQL Upsert
                stmt = insert(Retailer).values(values_to_insert)
                
                # কনফ্লিক্ট হলে কি কি আপডেট হবে
                update_cols = {k: v for k, v in values_to_insert.items() if k not in ['retailer_code', 'house_id']}
                update_cols['updated_at'] = func.now()

                stmt = stmt.on_conflict_do_update(
                    index_elements=['retailer_code'],
                    set_=update_cols
                )
                
                await session.execute(stmt)
                count += 1

                # ৫. লাইভ প্রগ্রেস আপডেট
                if progress_callback and (count % 10 == 0 or count == total_rows):
                    percent = round((count / total_rows) * 100)
                    await progress_callback(
                        f"⏳ **রিটেইলার আপলোড প্রগ্রেস:** {bn_num(percent)}%\n"
                        f"📈 প্রসেস হয়েছে: `{bn_num(count)}` / `{bn_num(total_rows)}`"
                    )

            await session.commit()
            logger.info(f"✅ House {house_id}: {bn_num(count)} retailers processed and linked via iTop.")
            return count, None

    except Exception as e:
        logger.error(f"❌ Retailer Excel Error: {str(e)}")
        return 0, f"{str(e)}"