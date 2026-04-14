import pandas as pd
import os
import asyncio
import logging
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from app.Models.field_force import FieldForce
from app.Models.retailer import Retailer 
from app.Models.user import User         
from app.Services.db_service import async_session

logger = logging.getLogger(__name__)

# ৩৮টি কলামের হেডার লিস্ট
FF_COLUMNS = [
    'DMS_CODE', 'AGENCY_ID', 'NAME', 'TYPE', 'PHONE_NUMBER', 'PERSONAL_NUMBER', 
    'POOL_NUMBER', 'ASSISTED_RETAILER_CODE', 'SALARY', 'MARKET_TYPE', 
    'JOINING_DATE', 'RESIGNED_DATE', 'RELIGION', 'DOB', 'NID',
    'BANK_NAME', 'BANK_ACCOUNT', 'BRANCH_NAME', 'ROUTING_NUMBER', 'HOME_TOWN',
    'EMERGENCY_CONTACT_PERSON_NAME', 'EMERGENCY_CONTACT_PERSON_NUMBER', 'RELATIONSHIP',
    'LAST_EDUCATION', 'INSTITUTION_NAME', 'BLOOD_GROUP', 'PRESENT_ADDRESS', 
    'PERMANENT_ADDRESS', 'FATHERS_NAME', 'MOTHERS_NAME', 'PREVIOUS_COMPANY_NAME', 
    'PREVIOUS_COMPANY_SALARY', 'MOTOR_BIKE', 'BICYCLE', 'DRIVING_LICENSE', 'STATUS'
]

async def generate_ff_sample(file_path):
    df = pd.DataFrame(columns=FF_COLUMNS)
    df.to_excel(file_path, index=False)
    return file_path

async def process_field_force_excel(file_path, house_id, progress_callback=None):
    try:
        # ১. ডাটা লোড ও কলাম ক্লিনআপ
        df = pd.read_excel(file_path, dtype=str).fillna("")
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
        
        total_rows = len(df)
        if total_rows == 0:
            return 0, "ফাইলটিতে কোনো ডাটা পাওয়া যায়নি।"

        async with async_session() as session:
            count = 0
            for index, row in df.iterrows():
                dms_code_val = row.get('DMS_CODE', '').strip()
                name_val = row.get('NAME', '').strip()
                
                if not dms_code_val or not name_val:
                    continue

                # ২. Retailer ID এবং User ID বের করা
                r_helper_code = row.get('ASSISTED_RETAILER_CODE', '').strip()
                target_retailer_id = None
                if r_helper_code:
                    r_res = await session.execute(
                        select(Retailer.id).where(Retailer.retailer_code == r_helper_code, Retailer.house_id == house_id)
                    )
                    target_retailer_id = r_res.scalar_one_or_none()

                p_phone = row.get('PERSONAL_NUMBER', '').strip()
                target_user_id = None
                if p_phone:
                    clean_phone = p_phone if p_phone.startswith('0') else f"0{p_phone}"
                    u_res = await session.execute(select(User.id).where(User.phone_number == clean_phone))
                    target_user_id = u_res.scalar_one_or_none()

                # ৩. ডাটা ডিকশনারি তৈরি (মডেলের কলাম নাম অনুযায়ী নিখুঁত ম্যাপিং) ✅
                # বি.প্র: মডেলের relationship এবং bicyle বানান চেক করা হয়েছে
                data_map = {
                    "house_id": house_id,
                    "user_id": target_user_id,
                    "retailer_id": target_retailer_id,
                    "dms_code": dms_code_val,
                    "agency_id": row.get('AGENCY_ID', '').strip(),
                    "name": name_val,
                    "type": row.get('TYPE', 'SR').strip().upper(),
                    "phone_number": row.get('PHONE_NUMBER', '').strip(),
                    "personal_number": p_phone,
                    "pool_number": row.get('POOL_NUMBER', '').strip(),
                    "salary": row.get('SALARY', '').strip(),
                    "market_type": row.get('MARKET_TYPE', '').strip(),
                    "joining_date": row.get('JOINING_DATE', '').strip(),
                    "resigned_date": row.get('RESIGNED_DATE', '').strip(),
                    "religion": row.get('RELIGION', '').strip(),
                    "dob": row.get('DOB', '').strip(),
                    "nid": row.get('NID', '').strip(),
                    "bank_name": row.get('BANK_NAME', '').strip(),
                    "bank_account": row.get('BANK_ACCOUNT', '').strip(),
                    "branch_name": row.get('BRANCH_NAME', '').strip(),
                    "routing_number": row.get('ROUTING_NUMBER', '').strip(),
                    "home_town": row.get('HOME_TOWN', '').strip(),
                    "emergency_contact_person_name": row.get('EMERGENCY_CONTACT_PERSON_NAME', '').strip(),
                    "emergency_contact_person_number": row.get('EMERGENCY_CONTACT_PERSON_NUMBER', '').strip(),
                    "relationship": row.get('RELATIONSHIP', '').strip(), # মডেল নাম: relationship ✅
                    "last_education": row.get('LAST_EDUCATION', '').strip(),
                    "institution_name": row.get('INSTITUTION_NAME', '').strip(),
                    "blood_group": row.get('BLOOD_GROUP', '').strip(),
                    "present_address": row.get('PRESENT_ADDRESS', '').strip(),
                    "permanent_address": row.get('PERMANENT_ADDRESS', '').strip(),
                    "fathers_name": row.get('FATHERS_NAME', '').strip(),
                    "mothers_name": row.get('MOTHERS_NAME', '').strip(),
                    "previous_company_name": row.get('PREVIOUS_COMPANY_NAME', '').strip(),
                    "previous_company_salary": row.get('PREVIOUS_COMPANY_SALARY', '').strip(),
                    "motor_bike": row.get('MOTOR_BIKE', '').strip(),
                    "bicyle": row.get('BICYCLE', '').strip(), # মডেল নাম: bicyle ✅
                    "driving_license": row.get('DRIVING_LICENSE', '').strip(),
                    "status": row.get('STATUS', 'Active').strip()
                }

                # ৪. SQL Statement তৈরি
                stmt = insert(FieldForce).values(**data_map)

                # ৫. আপডেট ডিকশনারি (যেগুলো কনফ্লিক্ট হলে পরিবর্তন করা যাবে)
                # dms_code এবং house_id বাদে বাকি সব আপডেট হবে
                update_cols = {k: v for k, v in data_map.items() if k not in ['dms_code', 'house_id']}
                update_cols['updated_at'] = func.now()

                # Upsert কার্যকর করা
                stmt = stmt.on_conflict_do_update(
                    index_elements=['dms_code'],
                    set_=update_cols
                )
                
                await session.execute(stmt)
                count += 1

                # ৬. লাইভ প্রগ্রেস আপডেট
                if progress_callback and (count % 10 == 0 or count == total_rows):
                    percent = round((count / total_rows) * 100)
                    progress_text = (
                        f"⏳ **আপলোড প্রগ্রেস:** {percent}%\n"
                        f"📈 প্রসেস হয়েছে: `{count}` / `{total_rows}`\n"
                        f"🏢 হাউজ আইডি: `{house_id}`"
                    )
                    await progress_callback(progress_text)

            await session.commit()
            return count, None

    except Exception as e:
        logger.error(f"❌ Excel Processing Error: {str(e)}")
        return 0, f"প্রসেসিং এরর: {str(e)}"