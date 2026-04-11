import pandas as pd
import os
import logging
from sqlalchemy.dialects.postgresql import insert
from app.Models.retailer import Retailer
from app.Services.db_service import async_session

logger = logging.getLogger(__name__)

async def process_retailer_excel(file_path, house_id):
    try:
        # এক্সেল রিড করা (Header গুলোকে আপারকেস করা যাতে ম্যচিং সহজ হয়)
        df = pd.read_excel(file_path, dtype=str).fillna("")
        df.columns = df.columns.str.replace(' ', '').str.upper()

        async with async_session() as session:
            count = 0
            for _, row in df.iterrows():
                # Upsert Logic: আরআইএম কোড ইউনিক কি হিসেবে কাজ করবে
                stmt = insert(Retailer).values(
                    house_id=house_id,
                    code=row.get('RETAILER_CODE'),
                    name=row.get('RETAILER_NAME'),
                    type=row.get('RETAILER_TYPE'),
                    enabled=row.get('ENABLED'),
                    sim_seller=row.get('SIM_SELLER'),
                    tran_mobile_no=row.get('TRANMOBILENO'),
                    itop_sr_number=row.get('I_TOP_UP_SR_NUMBER'),
                    itop_number=row.get('I_TOP_UP_NUMBER'),
                    service_point=row.get('SERVICE_POINT'),
                    category=row.get('CATEGORY'),
                    owner_name=row.get('OWNER_NAME'),
                    contact_no=row.get('CONTACT_NO'),
                    district=row.get('DISTRICT'),
                    thana=row.get('THANA'),
                    address=row.get('ADDRESS'),
                    nid=row.get('NID'),
                    bp_code=row.get('BP_CODE'),
                    bp_number=row.get('BP_NUMBER'),
                    dob=row.get('DOB'),
                    route=row.get('ROUTE')
                )
                
                # যদি কোড আগে থেকে থাকে তবে তথ্য আপডেট হবে
                stmt = stmt.on_conflict_do_update(
                    index_elements=['code'],
                    set_={
                        "name": stmt.excluded.name,
                        "enabled": stmt.excluded.enabled,
                        "contact_no": stmt.excluded.contact_no,
                        "itop_number": stmt.excluded.itop_number
                    }
                )
                await session.execute(stmt)
                count += 1
            
            await session.commit()
            return count, None
    except Exception as e:
        logger.error(f"Excel Error: {e}")
        return 0, str(e)