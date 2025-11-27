from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import async_playwright, Page, Browser
import re
import logging
import json
import sys
from pathlib import Path

from models.dog import Dog
from models.medicalRecord import MedicalRecord, MedicalRecordCreate
from core.database import session_scope
from utils.dog_matcher import find_existing_dog

root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

logger = logging.getLogger(__name__)

OFA_BASE_URL = "https://ofa.org"
OFA_SEARCH_URL = f"{OFA_BASE_URL}/advanced-search/"
OFA_DETAIL_URL = f"{OFA_BASE_URL}/advanced-search/"

class OFAParser:

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()

    async def search_dog_by_registration_number(self, registration_number: str) -> Optional[str]:
        try:
            await self.page.goto(OFA_SEARCH_URL, wait_until='networkidle')

            await self.page.fill('input[name="as_filter[regnum]"]', registration_number)

            await self.page.click('button[name="as_action[search]"]')
            await self.page.wait_for_load_state('networkidle')

            results_text = await self.page.text_content('#api_results')
            if results_text and 'matches' in results_text and '0 matches' not in results_text:
                result_row = await self.page.query_selector('.as_results_row')
                if result_row:
                    appnum = await result_row.get_attribute('data-appnum')
                    return appnum

            return None

        except Exception as e:
            logger.error(f"Error searching by registration number {registration_number}: {str(e)}")
            return None

    async def search_dog_by_name(self, dog_name: str) -> Optional[str]:
        try:
            await self.page.goto(OFA_SEARCH_URL, wait_until='networkidle')

            await self.page.fill('input[name="as_filter[regname]"]', dog_name)

            await self.page.click('button[name="as_action[search]"]')
            await self.page.wait_for_load_state('networkidle')

            results_text = await self.page.text_content('#api_results')
            if results_text and 'matches' in results_text and '0 matches' not in results_text:
                result_row = await self.page.query_selector('.as_results_row')
                if result_row:
                    appnum = await result_row.get_attribute('data-appnum')
                    return appnum

            return None

        except Exception as e:
            logger.error(f"Error searching by name {dog_name}: {str(e)}")
            return None

    async def search_dog_by_ofa_number(self, ofa_number: str) -> Optional[str]:
        try:
            await self.page.goto(OFA_SEARCH_URL, wait_until='networkidle')

            await self.page.fill('input[name="as_filter[ofanum]"]', ofa_number)

            await self.page.click('button[name="as_action[search]"]')
            await self.page.wait_for_load_state('networkidle')

            results_text = await self.page.text_content('#api_results')
            if results_text and 'matches' in results_text and '0 matches' not in results_text:
                result_row = await self.page.query_selector('.as_results_row')
                if result_row:
                    appnum = await result_row.get_attribute('data-appnum')
                    return appnum

            return None

        except Exception as e:
            logger.error(f"Error searching by OFA number {ofa_number}: {str(e)}")
            return None

    async def get_dog_details(self, appnum: str) -> Optional[Dict]:
        try:
            detail_url = f"{OFA_DETAIL_URL}?appnum={appnum}"
            await self.page.goto(detail_url, wait_until='networkidle')

            dog_info = await self._extract_dog_info()

            medical_records = await self._extract_medical_records()

            return {
                'appnum': appnum,
                'dog_info': dog_info,
                'medical_records': medical_records
            }

        except Exception as e:
            logger.error(f"Error getting dog details for appnum {appnum}: {str(e)}")
            return None

    async def _extract_dog_info(self) -> Dict:
        dog_info = {}

        try:
            name_element = await self.page.query_selector('h1, h2, .dog-name')
            if name_element:
                dog_info['name'] = await name_element.text_content()

        except Exception as e:
            logger.error(f"Error extracting dog info: {str(e)}")

        return dog_info

    async def _extract_medical_records(self) -> List[Dict]:
        medical_records = []

        try:
            await self.page.wait_for_selector('#as_detail_tests', timeout=10000)

            table_html = await self.page.inner_html('#as_detail_tests')
            soup = BeautifulSoup(table_html, 'html.parser')

            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 6:
                    record = {
                        'registry': cells[0].get_text(strip=True),
                        'test_date': self._parse_date(cells[1].get_text(strip=True)),
                        'report_date': self._parse_date(cells[2].get_text(strip=True)),
                        'age_in_months': self._parse_age(cells[3].get_text(strip=True)),
                        'conclusion': cells[4].get_text(strip=True),
                        'ofa_number': cells[5].get_text(strip=True)
                    }
                    medical_records.append(record)

        except Exception as e:
            logger.error(f"Error extracting medical records: {str(e)}")

        return medical_records

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str or date_str.strip() == '':
            return None

        try:
            date_str = date_str.strip()
            return datetime.strptime(date_str, "%b %d %Y")
        except ValueError:
            try:
                date_str = re.sub(r'\s+', ' ', date_str.strip())
                return datetime.strptime(date_str, "%b %d %Y")
            except ValueError as e:
                logger.warning(f"Could not parse date: {date_str}, error: {str(e)}")
                return None

    def _parse_age(self, age_str: str) -> Optional[int]:
        if not age_str or age_str.strip() == '':
            return None

        try:
            return int(age_str.strip())
        except ValueError as e:
            logger.warning(f"Could not parse age: {age_str}, error: {str(e)}")
            return None

async def search_and_parse_dog_medical_records(
    registration_number: Optional[str] = None,
    dog_name: Optional[str] = None,
    ofa_number: Optional[str] = None
) -> Optional[Dict]:

    async with OFAParser() as parser:
        appnum = None

        if registration_number:
            appnum = await parser.search_dog_by_registration_number(registration_number)

        if not appnum and dog_name:
            appnum = await parser.search_dog_by_name(dog_name)

        if not appnum and ofa_number:
            appnum = await parser.search_dog_by_ofa_number(ofa_number)

        if appnum:
            return await parser.get_dog_details(appnum)

        return None

async def save_medical_records_to_database(
    dog_id: int,
    medical_records: List[Dict],
    session: AsyncSession
) -> List[MedicalRecord]:
    saved_records = []

    try:
        for record_data in medical_records:
            existing_record = await session.execute(
                select(MedicalRecord).where(
                    MedicalRecord.dog_id == dog_id,
                    MedicalRecord.ofa_number == record_data.get('ofa_number')
                )
            )
            existing_record = existing_record.scalars().first()

            if existing_record:
                for key, value in record_data.items():
                    if hasattr(existing_record, key):
                        setattr(existing_record, key, value)
                saved_records.append(existing_record)
            else:
                record = MedicalRecord(
                    dog_id=dog_id,
                    **record_data
                )
                session.add(record)
                saved_records.append(record)

        await session.commit()
        logger.info(f"Saved {len(saved_records)} medical records for dog {dog_id}")

    except Exception as e:
        logger.error(f"Error saving medical records: {str(e)}")
        await session.rollback()

    return saved_records

async def process_dog_medical_records(
    dog_id: int,
    registration_number: Optional[str] = None,
    dog_name: Optional[str] = None,
    ofa_number: Optional[str] = None
) -> Dict:

    try:
        result = await search_and_parse_dog_medical_records(
            registration_number=registration_number,
            dog_name=dog_name,
            ofa_number=ofa_number
        )

        if not result:
            return {
                'success': False,
                'message': 'No medical records found',
                'dog_id': dog_id
            }

        async with session_scope() as session:
            saved_records = await save_medical_records_to_database(
                dog_id,
                result['medical_records'],
                session
            )

        return {
            'success': True,
            'message': f'Successfully processed {len(saved_records)} medical records',
            'dog_id': dog_id,
            'appnum': result['appnum'],
            'records_count': len(saved_records),
            'dog_info': result['dog_info']
        }

    except Exception as e:
        logger.error(f"Error processing medical records for dog {dog_id}: {str(e)}")
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'dog_id': dog_id
        }

async def batch_process_medical_records(dogs_data: List[Dict]) -> List[Dict]:
    results = []

    for dog_data in dogs_data:
        result = await process_dog_medical_records(
            dog_id=dog_data['dog_id'],
            registration_number=dog_data.get('registration_number'),
            dog_name=dog_data.get('registered_name'),
            ofa_number=dog_data.get('ofa_number')
        )
        results.append(result)

    return results

async def test_ofa_parser():
    result = await search_and_parse_dog_medical_records(
        registration_number="WS65203501"
    )

    if result:
        print(f"Found dog with appnum: {result['appnum']}")
        print(f"Dog info: {result['dog_info']}")
        print(f"Medical records: {json.dumps(result['medical_records'], indent=2, default=str)}")
    else:
        print("No results found")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_ofa_parser())