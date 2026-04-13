import pandas as pd
import os
from sqlalchemy.dialects.postgresql import insert
from app.Models.retailer import Retailer
from app.Services.db_service import async_session

RET_COLUMNS = [
    'RETAILER_CODE', 'RETAILER_NAME', 'RETAILER_TYPE', 'ENABLED', 'SIM_SELLER', 
    'TRANMOBILENO', 'I_TOP_UP_SR_NUMBER', 'I_TOP_UP_NUMBER', 'SERVICE_POINT', 
    'CATEGORY', 'OWNER_NAME', 'CONTACT_NO', 'DISTRICT', 'THANA', 'ADDRESS', 
    'NID', 'BP_CODE', 'BP_NUMBER', 'DOB', 'ROUTE'
]

async def generate_retailer_sample(file_path):
    df = pd.DataFrame(columns=RET_COLUMNS)
    df.to_excel(file_path, index=False)
    return file_path

async def process_retailer_excel(file_path, house_id):
    try:
        df = pd.read_excel(file_path, dtype=str).fillna("")
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

        async with async_session() as session:
            count = 0
            for _, row in df.iterrows():
                code = row.get('RETAILER_CODE', '').strip()
                if not code: continue
                
                stmt = insert(Retailer).values(
                    house_id=house_id,
                    code=code,
                    name=row.get('RETAILER_NAME', ''),
                    type=row.get('RETAILER_TYPE', ''),
                    enabled=row.get('ENABLED', ''),
                    sim_seller=row.get('SIM_SELLER', ''),
                    tran_mobile_no=row.get('TRANMOBILENO', ''),
                    itop_sr_number=row.get('I_TOP_UP_SR_NUMBER', ''),
                    itop_number=row.get('I_TOP_UP_NUMBER', ''),
                    service_point=row.get('SERVICE_POINT', ''),
                    category=row.get('CATEGORY', ''),
                    owner_name=row.get('OWNER_NAME', ''),
                    contact_no=row.get('CONTACT_NO', ''),
                    district=row.get('DISTRICT', ''),
                    thana=row.get('THANA', ''),
                    address=row.get('ADDRESS', ''),
                    nid=row.get('NID', ''),
                    bp_code=row.get('BP_CODE', ''),
                    bp_number=row.get('BP_NUMBER', ''),
                    dob=row.get('DOB', ''),
                    route=row.get('ROUTE', '')
                )

                # Upsert: কোড মিলে গেলে তথ্য আপডেট হবে
                stmt = stmt.on_conflict_do_update(
                    index_elements=['code'],
                    set_={col.lower(): getattr(stmt.excluded, col.lower()) for col in df.columns if col in RET_COLUMNS}
                )
                await session.execute(stmt)
                count += 1
            
            await session.commit()
            return count, None
    except Exception as e:
        return 0, str(e)