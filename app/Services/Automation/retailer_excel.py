import pandas as pd
import os
import logging
from sqlalchemy.dialects.postgresql import insert
from app.Models.retailer import Retailer
from app.Services.db_service import async_session

logger = logging.getLogger(__name__)

# এক্সেল হেডার এবং ডাটাবেজ কলামের নিখুঁত ম্যাপিং ✅
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

async def process_retailer_excel(file_path, house_id):
    try:
        # ১. এক্সেল ফাইল রিড করা
        df = pd.read_excel(file_path, dtype=str).fillna("")
        # হেডারের স্পেস রিমুভ এবং বড় হাতের করা
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

        async with async_session() as session:
            count = 0
            for _, row in df.iterrows():
                # আর-কোড না থাকলে স্কিপ করবে
                r_code = str(row.get('RETAILER_CODE', '')).strip()
                if not r_code: continue

                # ২. ইনসার্ট ডাটা তৈরি করা
                values_to_insert = {"house_id": house_id}
                
                # লুপ চালিয়ে ম্যাপ অনুযায়ী ডাটা নেওয়া
                for excel_header, db_col in COLUMN_MAP.items():
                    values_to_insert[db_col] = str(row.get(excel_header, '')).strip()

                # ৩. PostgreSQL Upsert (থাকলে আপডেট, না থাকলে ইনসার্ট)
                stmt = insert(Retailer).values(values_to_insert)
                
                # কনফ্লিক্ট হলে কোন কোন কলাম আপডেট হবে
                update_cols = {
                    "name": stmt.excluded.name,
                    "enabled": stmt.excluded.enabled,
                    "contact_no": stmt.excluded.contact_no,
                    "itop_number": stmt.excluded.itop_number,
                    "address": stmt.excluded.address,
                    "route": stmt.excluded.route
                }

                stmt = stmt.on_conflict_do_update(
                    index_elements=['retailer_code'], # ইউনিক কি: রিটেইলার কোড
                    set_=update_cols
                )
                
                await session.execute(stmt)
                count += 1
            
            await session.commit()
            logger.info(f"✅ House {house_id}: {count} retailers processed from Excel.")
            return count, None

    except Exception as e:
        logger.error(f"❌ Retailer Excel Processing Error: {str(e)}")
        return 0, str(e)
