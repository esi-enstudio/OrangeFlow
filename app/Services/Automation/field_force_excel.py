import pandas as pd
import os
import asyncio
import logging
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from app.Models.field_force import FieldForce
from app.Models.user import User         
from app.Services.db_service import async_session

logger = logging.getLogger(__name__)

# ৩৮টি কলামের হেডার লিস্ট
FF_COLUMNS = [
    'DMS_CODE', 'AGENCY_ID', 'NAME', 'TYPE', 'ITOP_NUMBER', 'PERSONAL_NUMBER', 
    'POOL_NUMBER', 'ASSISTED_RETAILER_CODE', 'SALARY', 'MARKET_TYPE', 
    'JOINING_DATE', 'RESIGNED_DATE', 'RELIGION', 'DOB', 'NID',
    'BANK_NAME', 'BANK_ACCOUNT', 'BRANCH_NAME', 'ROUTING_NUMBER', 'HOME_TOWN',
    'EMERGENCY_CONTACT_PERSON_NAME', 'EMERGENCY_CONTACT_PERSON_NUMBER', 'RELATIONSHIP',
    'LAST_EDUCATION', 'INSTITUTION_NAME', 'BLOOD_GROUP', 'PRESENT_ADDRESS', 
    'PERMANENT_ADDRESS', 'FATHERS_NAME', 'MOTHERS_NAME', 'PREVIOUS_COMPANY_NAME', 
    'PREVIOUS_COMPANY_SALARY', 'MOTOR_BIKE', 'BICYCLE', 'DRIVING_LICENSE', 'STATUS'
]

async def generate_ff_sample(file_path):
    """স্যাম্পল এক্সել ফাইল তৈরি"""
    df = pd.DataFrame(columns=FF_COLUMNS)
    df.to_excel(file_path, index=False)
    return file_path

async def process_field_force_excel(file_path, house_id, progress_callback=None):
    """এক্সেল ফাইল থেকে ডাটা নিয়ে ডাটাবেজে Upsert করবে"""
    try:
        # ১. ডাটা লোড
        df = pd.read_excel(file_path, dtype=str)
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
        
        total_rows = len(df)
        if total_rows == 0: return 0, "ফাইলটিতে কোনো ডাটা পাওয়া যায়নি।"

        # ২. ক্লিন ফাংশন
        def clean_val(val):
            if pd.isna(val): 
                return None
            v = str(val).strip()
            if v == "" or v.lower() in ["nan", "none", "null"]:
                return None
            return v

        async with async_session() as session:
            # এখানে count ইনিশিয়ালাইজ করা হয়েছে ✅
            count = 0
            
            for index, row in df.iterrows():
                dms_code_val = clean_val(row.get('DMS_CODE'))
                name_val = clean_val(row.get('NAME'))
                
                if not dms_code_val or not name_val: continue

                # ৩. User ID বের করা
                p_phone_raw = clean_val(row.get('PERSONAL_NUMBER'))
                target_user_id = None
                if p_phone_raw:
                    clean_p_phone = p_phone_raw if p_phone_raw.startswith('0') else f"0{p_phone_raw}"
                    u_res = await session.execute(select(User.id).where(User.phone_number == clean_p_phone))
                    target_user_id = u_res.scalar_one_or_none()

                # ৪. ডাটাবেজ ম্যাপ
                data_map = {
                    "house_id": house_id,
                    "user_id": target_user_id,
                    "dms_code": dms_code_val,
                    "assisted_retailer_code": clean_val(row.get('ASSISTED_RETAILER_CODE')),
                    "agency_id": clean_val(row.get('AGENCY_ID')),
                    "name": name_val,
                    "itop_number": clean_val(row.get('ITOP_NUMBER')),
                    "personal_number": p_phone_raw,
                    "pool_number": clean_val(row.get('POOL_NUMBER')),
                    "type": (clean_val(row.get('TYPE')) or "SR").upper(),
                    "status": clean_val(row.get('STATUS')) or "Active",
                    "bank_name": clean_val(row.get('BANK_NAME')),
                    "bank_account": clean_val(row.get('BANK_ACCOUNT')),
                    "branch_name": clean_val(row.get('BRANCH_NAME')),
                    "routing_number": clean_val(row.get('ROUTING_NUMBER')),
                    "home_town": clean_val(row.get('HOME_TOWN')),
                    "emergency_contact_person_name": clean_val(row.get('EMERGENCY_CONTACT_PERSON_NAME')),
                    "emergency_contact_person_number": clean_val(row.get('EMERGENCY_CONTACT_PERSON_NUMBER')),
                    "emergency_person_relationship": clean_val(row.get('RELATIONSHIP')),
                    "last_education": clean_val(row.get('LAST_EDUCATION')),
                    "institution_name": clean_val(row.get('INSTITUTION_NAME')),
                    "blood_group": clean_val(row.get('BLOOD_GROUP')),
                    "present_address": clean_val(row.get('PRESENT_ADDRESS')),
                    "permanent_address": clean_val(row.get('PERMANENT_ADDRESS')),
                    "fathers_name": clean_val(row.get('FATHERS_NAME')),
                    "mothers_name": clean_val(row.get('MOTHERS_NAME')),
                    "religion": clean_val(row.get('RELIGION')),
                    "dob": clean_val(row.get('DOB')),
                    "nid": clean_val(row.get('NID')),
                    "previous_company_name": clean_val(row.get('PREVIOUS_COMPANY_NAME')),
                    "previous_company_salary": clean_val(row.get('PREVIOUS_COMPANY_SALARY')),
                    "motor_bike": clean_val(row.get('MOTOR_BIKE')),
                    "bicyle": clean_val(row.get('BICYCLE')),
                    "driving_license": clean_val(row.get('DRIVING_LICENSE')),
                    "joining_date": clean_val(row.get('JOINING_DATE')),
                    "resigned_date": clean_val(row.get('RESIGNED_DATE')),
                    "market_type": clean_val(row.get('MARKET_TYPE')),
                    "salary": clean_val(row.get('SALARY')),
                }

                # ৫. SQL Upsert
                stmt = insert(FieldForce).values(**data_map)
                update_cols = {k: v for k, v in data_map.items() if k not in ['dms_code', 'house_id']}
                update_cols['updated_at'] = func.now()

                stmt = stmt.on_conflict_do_update(index_elements=['dms_code'], set_=update_cols)
                await session.execute(stmt)
                count += 1

                # ৬. প্রগ্রেস আপডেট
                if progress_callback and (count % 10 == 0 or count == total_rows):
                    percent = round((count / total_rows) * 100)
                    await progress_callback(f"⏳ **আপলোড প্রগ্রেস:** {percent}%\n📈 প্রসেস হয়েছে: `{count}` / `{total_rows}`")

            await session.commit()
            return count, None

    except Exception as e:
        logger.error(f"❌ Excel Processing Error: {str(e)}")
        return 0, f"প্রসেসিং এরর: {str(e)}"