import pandas as pd
import os
from sqlalchemy.dialects.postgresql import insert
from app.Models.field_force import FieldForce
from app.Services.db_service import async_session

# ৩৮টি কলামের হেডার লিস্ট
FF_COLUMNS = [
    'CODE', 'NAME', 'TYPE', 'PHONE_NUMBER', 'PERSONAL_NUMBER', 'POOL_NUMBER', 
    'SALARY', 'MARKET_TYPE', 'JOINING_DATE', 'RESIGNED_DATE', 'RELIGION', 'DOB', 'NID',
    'BANK_NAME', 'BANK_ACCOUNT', 'BRANCH_NAME', 'ROUTING_NUMBER', 'HOME_TOWN',
    'EMERGENCY_CONTACT_PERSON_NAME', 'EMERGENCY_CONTACT_PERSON_NUMBER', 'RELATIONSHIP',
    'LAST_EDUCATION', 'INSTITUTION_NAME', 'BLOOD_GROUP', 'PRESENT_ADDRESS', 
    'PERMANENT_ADDRESS', 'FATHERS_NAME', 'MOTHERS_NAME', 'PREVIOUS_COMPANY_NAME', 
    'PREVIOUS_COMPANY_SALARY', 'MOTOR_BIKE', 'BICYCLE', 'DRIVING_LICENSE', 'STATUS'
]

async def generate_ff_sample(file_path):
    """একটি স্যাম্পল এক্সেল ফাইল তৈরি করবে"""
    df = pd.DataFrame(columns=FF_COLUMNS)
    df.to_excel(file_path, index=False)
    return file_path

async def process_field_force_excel(file_path, house_id):
    """এক্সেল ফাইল থেকে ডাটা নিয়ে ডাটাবেজে Upsert করবে"""
    try:
        df = pd.read_excel(file_path, dtype=str).fillna("")
        # কলাম নাম ক্লিন করা
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

        async with async_session() as session:
            count = 0
            for _, row in df.iterrows():
                if not row.get('CODE') or not row.get('NAME'): continue
                
                stmt = insert(FieldForce).values(
                    house_id=house_id,
                    code=row.get('CODE'),
                    name=row.get('NAME'),
                    type=row.get('TYPE', 'SR'),
                    phone_number=row.get('PHONE_NUMBER'),
                    personal_number=row.get('PERSONAL_NUMBER'),
                    pool_number=row.get('POOL_NUMBER'),
                    salary=row.get('SALARY'),
                    market_type=row.get('MARKET_TYPE'),
                    joining_date=row.get('JOINING_DATE'),
                    resigned_date=row.get('RESIGNED_DATE'),
                    religion=row.get('RELIGION'),
                    dob=row.get('DOB'),
                    nid=row.get('NID'),
                    bank_name=row.get('BANK_NAME'),
                    bank_account=row.get('BANK_ACCOUNT'),
                    branch_name=row.get('BRANCH_NAME'),
                    routing_number=row.get('ROUTING_NUMBER'),
                    home_town=row.get('HOME_TOWN'),
                    emergency_contact_person_name=row.get('EMERGENCY_CONTACT_PERSON_NAME'),
                    emergency_contact_person_number=row.get('EMERGENCY_CONTACT_PERSON_NUMBER'),
                    relationship=row.get('RELATIONSHIP'),
                    last_education=row.get('LAST_EDUCATION'),
                    institution_name=row.get('INSTITUTION_NAME'),
                    blood_group=row.get('BLOOD_GROUP'),
                    present_address=row.get('PRESENT_ADDRESS'),
                    permanent_address=row.get('PERMANENT_ADDRESS'),
                    fathers_name=row.get('FATHERS_NAME'),
                    mothers_name=row.get('MOTHERS_NAME'),
                    previous_company_name=row.get('PREVIOUS_COMPANY_NAME'),
                    previous_company_salary=row.get('PREVIOUS_COMPANY_SALARY'),
                    motor_bike=row.get('MOTOR_BIKE'),
                    bicyle=row.get('BICYCLE'),
                    driving_license=row.get('DRIVING_LICENSE'),
                    status=row.get('STATUS', 'Active')
                )

                # যদি কোড আগে থেকে থাকে তবে আপডেট হবে (Upsert)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['code'],
                    set_={col.lower(): getattr(stmt.excluded, col.lower()) for col in FF_COLUMNS if col != 'CODE'}
                )
                await session.execute(stmt)
                count += 1
            
            await session.commit()
            return count, None
    except Exception as e:
        return 0, str(e)