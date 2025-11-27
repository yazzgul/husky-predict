from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathlib import Path
import re
import logging
import json
import sys

from models.dog import Dog, DogSiblingLink
from models.people import Breeder, Owner
from models.litters import Litter
from models.associations import DogBreederLink, DogOwnerLink
from core.parsersConfig import HUSKY_PEDIGREE_NET_API, HUSKY_PEDIGREE_NET_DOG_PATH
from core.database import session_scope
from utils.dog_matcher import find_existing_dog, detect_conflicts, merge_dog_data

root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

logger = logging.getLogger(__name__)

dog_page_url = f"{HUSKY_PEDIGREE_NET_API}{HUSKY_PEDIGREE_NET_DOG_PATH}"
gen_param = 3

async def fetch_dog_page(session: AsyncClient, dog_id: str) -> str:
    url = f"{dog_page_url}{dog_id}&gen={gen_param}"
    response = await session.get(url)
    response.raise_for_status()
    return response.text

async def fetch_dog_page_by_url(session: AsyncClient, url: str) -> str:
    response = await session.get(url)
    response.raise_for_status()
    return response.text

def generate_uuid_from_id(dog_id: str) -> str:
    import hashlib
    return hashlib.md5(f"huskypedigree_{dog_id}".encode()).hexdigest()

def generate_uuid_from_name(name: str) -> str:
    import hashlib
    return hashlib.md5(f"huskypedigree_{name}".encode()).hexdigest()

async def parse_coi(session: AsyncClient, dog_id: str) -> Optional[float]:
    try:
        from playwright.async_api import async_playwright
        
        analysis_url = f"{HUSKY_PEDIGREE_NET_API}/analiza.php?id={dog_id}&gen=12"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(analysis_url, wait_until='networkidle')
            
            await page.wait_for_selector('h3.result span#result', timeout=10000)
            
            coi_text = await page.text_content('h3.result span#result')
            
            await browser.close()
            
            if coi_text:
                print(f"COI text found: {coi_text}")
                match = re.search(r'F\s*=\s*([\d.]+)%', coi_text)
                if match:
                    coi_percentage = float(match.group(1))
                    coi_decimal = coi_percentage / 100.0
                    return coi_decimal
        
        return None
    except Exception as e:
        logger.warning(f"Could not parse COI for dog {dog_id}: {str(e)}")
        return None

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        date_str = date_str.strip().rstrip('.')
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError as e:
        logger.warning(f"Could not parse date: {date_str}, error: {str(e)}")
        return None

def parse_float(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

def extract_call_name(name_text: str) -> Optional[str]:
    if not name_text:
        return None
    match = re.search(r'\(([^)]+)\)', name_text)
    return match.group(1) if match else None

async def parse_dog_info(session: AsyncClient, soup: BeautifulSoup, dog_id: str) -> Dict:
    info = {}
    info['uuid'] = dog_id
    
    sadrzaj_div = soup.find('div', class_='sadrzaj')
    if sadrzaj_div:
        title_h2 = sadrzaj_div.find('h2')
        if title_h2:
            info['registered_name'] = title_h2.get_text(strip=True)
    
    data_table = soup.find('table', class_='podaci')
    
    if data_table:
        for row in data_table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower().rstrip(':')
                value_cell = cells[1]
                value = value_cell.get_text(strip=True)
                
                if label == 'reg.no':
                    info['registration_number'] = value
                elif label == 'name':
                    info['call_name'] = extract_call_name(value)
                elif label == 'sex':
                    info['sex'] = 1 if 'male' in value.lower() else 2
                elif label == 'colour':
                    info['color'] = value
                elif label == 'eyes':
                    info['eyes_color'] = value
                elif label == 'born':
                    info['date_of_birth'] = parse_date(value)
                elif label == 'breeder':
                    info['breeder'] = value
                    breeder_link = value_cell.find('a', href=True)
                    if breeder_link:
                        info['breeder_url'] = f"{HUSKY_PEDIGREE_NET_API}/{breeder_link['href']}"
                elif label == 'owner':
                    info['owner'] = value
                    owner_link = value_cell.find('a', href=True)
                    if owner_link:
                        info['owner_url'] = f"{HUSKY_PEDIGREE_NET_API}/{owner_link['href']}"
                elif label == 'ch-titles':
                    info['other_titles'] = value
                elif label == 'results':
                    if 'other_titles' in info:
                        info['other_titles'] += f"; {value}"
                    else:
                        info['other_titles'] = value
                elif label == 'height':
                    info['size'] = parse_float(value)
                elif label == 'note':
                    info['notes'] = value
    
    right_cell = soup.find('td', class_='right')

    if right_cell:
        photo_links = right_cell.find_all('a', onclick=True)
        photo_urls = []
        for link in photo_links:
            onclick = link.get('onclick', '')
            match = re.search(r'photo\((\d+),\s*(\d+),', onclick)
            if match:
                img_id = match.group(2)
                photo_url = f"{HUSKY_PEDIGREE_NET_API}/slike/{img_id}/{dog_id}.jpg"
                photo_urls.append(photo_url)
        if photo_urls:
            info['photo_url'] = ';'.join(photo_urls)
    
    coi = await parse_coi(session, dog_id)
    if coi is not None:
        info['coi'] = coi
    
    return info

def parse_pedigree_table(soup: BeautifulSoup, max_depth: int = 3) -> Dict:
    pedigree = {
        'sire': None, 
        'dam': None,
        'sire_uuid': None,
        'sire_name': None,
        'dam_uuid': None,
        'dam_name': None
    }
    
    pedigree_table = soup.find('table', class_='pedigre')
    if not pedigree_table:
        return pedigree
    
    expected_rowspan = 2 ** (gen_param - 1)
    
    rows = pedigree_table.find_all('tr')
    if not rows:
        return pedigree
    
    parent_count = 0
    
    for row in rows:
        cells = row.find_all('td')
        for cell in cells:
            rowspan = cell.get('rowspan')
            if rowspan and int(rowspan) == expected_rowspan:
                link = cell.find('a', href=True)
                if link:
                    href = link['href']
                    name = link.get_text(strip=True)
                    
                    match = re.search(r'id=(\d+)', href)
                    if match:
                        dog_id = match.group(1)
                        # parent is usually sire, second is dam
                        if parent_count == 0:
                            pedigree['sire_uuid'] = dog_id
                            pedigree['sire_name'] = name
                            pedigree['sire'] = {
                                'uuid': dog_id,
                                'name': name,
                                'url': f"{HUSKY_PEDIGREE_NET_API}/{href}"
                            }
                            parent_count += 1
                        elif parent_count == 1:
                            pedigree['dam_uuid'] = dog_id
                            pedigree['dam_name'] = name
                            pedigree['dam'] = {
                                'uuid': dog_id,
                                'name': name,
                                'url': f"{HUSKY_PEDIGREE_NET_API}/{href}"
                            }
                            parent_count += 1
                            break
                break
    
    return pedigree

def parse_offspring_table(soup: BeautifulSoup) -> List[Dict]:
    litters = []
    
    offspring_h3 = soup.find('h3', string=re.compile(r'offspring', re.IGNORECASE))
    if not offspring_h3:
        return litters
    
    offspring_table = offspring_h3.find_next('table')
    if not offspring_table:
        return litters
    
    litter_groups = {}
    
    rows = offspring_table.find_all('tr')
    for row in rows:
        if 'legenda' in row.get('class', []):
            continue
        
        cells = row.find_all('td')
        if len(cells) < 6:
            continue
        
        registration_number = cells[0].get_text(strip=True)
        name_cell = cells[2]
        name_link = name_cell.find('a', href=True)
        if not name_link:
            continue
        
        name = name_link.get_text(strip=True)
        href = name_link['href']
        match = re.search(r'id=(\d+)', href)
        if not match:
            continue
        
        puppy_id = match.group(1)
        
        # Extract sex
        sex_img = cells[3].find('img')
        sex = 1 if sex_img and 'sp1' in sex_img.get('src', '') else 2
        
        # Extract color
        color_img = cells[4].find('img', class_='boja')
        color = color_img.get('alt', '') if color_img else ''
        
        # Extract birth date
        birth_date = cells[5].get_text(strip=True)
        birth_date = parse_date(birth_date)
        
        # Extract sire
        sire_cell = cells[9] if len(cells) > 9 else None
        sire_name = None
        sire_id = None
        if sire_cell:
            sire_link = sire_cell.find('a', href=True)
            if sire_link:
                sire_name = sire_link.get_text(strip=True)
                sire_href = sire_link['href']
                sire_match = re.search(r'id=(\d+)', sire_href)
                if sire_match:
                    sire_id = sire_match.group(1)
        
        if birth_date:
            date_key = birth_date.strftime('%Y-%m-%d')
            if date_key not in litter_groups:
                litter_groups[date_key] = {
                    'date_of_birth': birth_date,
                    'puppies': []
                }
            
            puppy_data = {
                'uuid': puppy_id,
                'registered_name': name,
                'registration_number': registration_number,
                'sex': sex,
                'color': color,
                'date_of_birth': birth_date,
                'sire_name': sire_name,
                'sire_uuid': sire_id
            }
            
            litter_groups[date_key]['puppies'].append(puppy_data)
    
    for date_key, group in litter_groups.items():
        litter = {
            'date_of_birth': group['date_of_birth'],
            'puppies': group['puppies']
        }
        litters.append(litter)
    
    return litters

async def save_to_database(dog_data: Dict, session: AsyncSession) -> Optional[Dog]:
    try:
        existing_dog, match_method, similarity = await find_existing_dog(
            session, dog_data, "husky.pedigre.net"
        )
        
        if existing_dog:
            logger.info(f"Found existing dog by {match_method} (similarity: {similarity:.2f}): {existing_dog.registered_name}")
            
            has_conflicts, conflicts = detect_conflicts(existing_dog, dog_data, "husky.pedigre.net")
            
            if has_conflicts:
                logger.warning(f"Conflicts detected for dog {existing_dog.registered_name}: {conflicts}")
                existing_dog.has_conflicts = True
                if existing_dog.conflicts is None:
                    existing_dog.conflicts = {}
                
                for field, field_conflicts in conflicts.items():
                    if field not in existing_dog.conflicts:
                        existing_dog.conflicts[field] = {}
                    existing_dog.conflicts[field].update(field_conflicts)
            
            has_changes, _ = merge_dog_data(existing_dog, dog_data, "husky.pedigre.net")
            
            if has_changes:
                await session.flush()
                logger.info(f"Updated existing dog {existing_dog.registered_name} with new data")
            
            dog = existing_dog
        else:
            # Create new dog
            dog = Dog(**{k: v for k, v in dog_data.items() if k not in ['breeders', 'owners', 'siblings', 'litters', 'sire', 'dam']})
            session.add(dog)
            await session.flush()
            await session.refresh(dog)
            logger.info(f"Created new dog: {dog.registered_name}")

        async def handle_breeders(breeders_data: List[Dict], dog_id: int):
            dog_check = await session.execute(select(Dog).where(Dog.id == dog_id))
            if not dog_check.scalars().first():
                logger.error(f"Dog with ID {dog_id} does not exist, cannot create breeder links")
                return
                
            for breeder_data in breeders_data:
                breeder_uuid = breeder_data.get('uuid')
                if not breeder_uuid:
                    breeder_uuid = generate_uuid_from_name(breeder_data.get('name', ''))
                    breeder_data['uuid'] = breeder_uuid
                result = await session.execute(select(Breeder).where(Breeder.uuid == breeder_uuid))
                breeder = result.scalars().first()
                if not breeder:
                    breeder = Breeder(**breeder_data)
                    session.add(breeder)
                    await session.flush()
                    await session.refresh(breeder)
                await session.execute(delete(DogBreederLink).where(DogBreederLink.dog_id == dog_id))
                session.add(DogBreederLink(dog_id=dog_id, breeder_id=breeder.id))
            await session.flush()

        async def handle_owners(owners_data: List[Dict], dog_id: int):
            dog_check = await session.execute(select(Dog).where(Dog.id == dog_id))
            if not dog_check.scalars().first():
                logger.error(f"Dog with ID {dog_id} does not exist, cannot create owner links")
                return
                
            for owner_data in owners_data:
                owner_uuid = owner_data.get('uuid')
                if not owner_uuid:
                    owner_uuid = generate_uuid_from_name(owner_data.get('name', ''))
                    owner_data['uuid'] = owner_uuid
                result = await session.execute(select(Owner).where(Owner.uuid == owner_uuid))
                owner = result.scalars().first()
                if not owner:
                    owner = Owner(**owner_data)
                    session.add(owner)
                    await session.flush()
                    await session.refresh(owner)
                await session.execute(delete(DogOwnerLink).where(DogOwnerLink.dog_id == dog_id))
                session.add(DogOwnerLink(dog_id=dog_id, owner_id=owner.id))
            await session.flush()

        async def handle_litters(litters_data: List[Dict], dog_id: int, is_sire: bool = False, is_dam: bool = False):
            dog_check = await session.execute(select(Dog).where(Dog.id == dog_id))
            if not dog_check.scalars().first():
                logger.error(f"Dog with ID {dog_id} does not exist, cannot create litter links")
                return
                
            for litter_data in litters_data:
                puppies = litter_data.pop('puppies', [])
                litter = Litter(**litter_data)
                
                if is_sire:
                    litter.sire_id = dog_id
                if is_dam:
                    litter.dam_id = dog_id

                if puppies and not (is_sire or is_dam):
                    for puppy_data in puppies:
                        if 'sire_uuid' in puppy_data:
                            sire = await save_to_database(puppy_data, session)
                            if sire:
                                litter.sire_id = sire.id
                        break

                session.add(litter)
                await session.flush()
                await session.refresh(litter)
                
                for puppy_data in puppies:
                    existing_puppy, _, _ = await find_existing_dog(session, puppy_data, "husky.pedigre.net")
                    if existing_puppy:
                        puppy = existing_puppy
                    else:
                        puppy = Dog(**{k: v for k, v in puppy_data.items() if k not in ['breeders', 'owners', 'siblings', 'litters', 'sire', 'dam']})
                        session.add(puppy)
                        await session.flush()
                        await session.refresh(puppy)
                    puppy.birth_litter_id = litter.id
                    session.add(puppy)
                await session.flush()

        if dog_data.get('sire'):
            sire = await save_to_database(dog_data['sire'], session)
            if sire:
                dog.sire_id = sire.id
                await session.flush()
            
        if dog_data.get('dam'):
            dam = await save_to_database(dog_data['dam'], session)
            if dam:
                dog.dam_id = dam.id
                await session.flush()

        if dog_data.get('breeders'):
            await handle_breeders(dog_data['breeders'], dog.id)
        if dog_data.get('owners'):
            await handle_owners(dog_data['owners'], dog.id)
        
        if dog_data.get('litters'):
            await handle_litters(dog_data['litters'], dog.id, is_sire=(dog.sex == 1), is_dam=(dog.sex == 2))

        await session.commit()
        return dog
    except Exception as e:
        logger.error(f"Error saving to database: {str(e)}")
        await session.rollback()
        return None

def map_to_dog_model(parsed_data: Dict, depth: int = 0, max_depth: int = 3) -> Dict:
    dog_info = parsed_data.get('dog_info', {})
    pedigree = parsed_data.get('pedigree', {})
    litters = parsed_data.get('litters', [])

    dog_data = {
        'uuid': dog_info.get('uuid'),
        'registered_name': dog_info.get('registered_name'),
        'call_name': dog_info.get('call_name'),
        'sex': dog_info.get('sex'),
        'date_of_birth': dog_info.get('date_of_birth'),
        'color': dog_info.get('color'),
        'eyes_color': dog_info.get('eyes_color'),
        'size': dog_info.get('size'),
        'other_titles': dog_info.get('other_titles'),
        'registration_number': dog_info.get('registration_number'),
        'photo_url': dog_info.get('photo_url'),
        'notes': dog_info.get('notes'),
        'coi': dog_info.get('coi'),
        'source': 'husky.pedigre.net',
        'sire_uuid': pedigree.get('sire_uuid'),
        'sire_name': pedigree.get('sire_name'),
        'dam_uuid': pedigree.get('dam_uuid'),
        'dam_name': pedigree.get('dam_name'),
    }
    
    # Breeders
    breeder_name = dog_info.get('breeder')
    if breeder_name:
        dog_data['breeders'] = [{'name': breeder_name, 'is_breeder': True, 'uuid': generate_uuid_from_name(breeder_name)}]
    else:
        dog_data['breeders'] = []
    
    # Owners
    owner_name = dog_info.get('owner')
    if owner_name:
        dog_data['owners'] = [{'name': owner_name, 'is_main_owner': True, 'uuid': generate_uuid_from_name(owner_name)}]
    else:
        dog_data['owners'] = []
    
    if depth < max_depth:
        if pedigree.get('sire') and pedigree['sire'].get('dog_info'):
            sire_info = pedigree['sire']['dog_info']
            sire_litters = pedigree['sire'].get('litters', [])
            dog_data['sire'] = {
                'uuid': sire_info.get('uuid'),
                'registered_name': sire_info.get('registered_name'),
                'call_name': sire_info.get('call_name'),
                'sex': sire_info.get('sex'),
                'date_of_birth': sire_info.get('date_of_birth'),
                'color': sire_info.get('color'),
                'eyes_color': sire_info.get('eyes_color'),
                'size': sire_info.get('size'),
                'other_titles': sire_info.get('other_titles'),
                'registration_number': sire_info.get('registration_number'),
                'photo_url': sire_info.get('photo_url'),
                'notes': sire_info.get('notes'),
                'coi': sire_info.get('coi'),
                'source': 'husky.pedigre.net',
                'litters': sire_litters
            }
            if pedigree['sire'].get('parents'):
                sire_parents = map_to_dog_model({'dog_info': {}, 'pedigree': pedigree['sire']['parents']}, depth + 1, max_depth)
                if sire_parents.get('sire'):
                    dog_data['sire']['sire'] = sire_parents['sire']
                if sire_parents.get('dam'):
                    dog_data['sire']['dam'] = sire_parents['dam']
        
        if pedigree.get('dam') and pedigree['dam'].get('dog_info'):
            dam_info = pedigree['dam']['dog_info']
            dam_litters = pedigree['dam'].get('litters', [])
            dog_data['dam'] = {
                'uuid': dam_info.get('uuid'),
                'registered_name': dam_info.get('registered_name'),
                'call_name': dam_info.get('call_name'),
                'sex': dam_info.get('sex'),
                'date_of_birth': dam_info.get('date_of_birth'),
                'color': dam_info.get('color'),
                'eyes_color': dam_info.get('eyes_color'),
                'size': dam_info.get('size'),
                'other_titles': dam_info.get('other_titles'),
                'registration_number': dam_info.get('registration_number'),
                'photo_url': dam_info.get('photo_url'),
                'notes': dam_info.get('notes'),
                'coi': dam_info.get('coi'),
                'source': 'husky.pedigre.net',
                'litters': dam_litters
            }
            if pedigree['dam'].get('parents'):
                dam_parents = map_to_dog_model({'dog_info': {}, 'pedigree': pedigree['dam']['parents']}, depth + 1, max_depth)
                if dam_parents.get('sire'):
                    dog_data['dam']['sire'] = dam_parents['sire']
                if dam_parents.get('dam'):
                    dog_data['dam']['dam'] = dam_parents['dam']
    
    # Litters
    dog_data['litters'] = litters
    
    return dog_data

async def parse_pedigree_recursive(session: AsyncClient, soup: BeautifulSoup, processed_urls: set, pedigree_depth: int = 3) -> Dict:
    if pedigree_depth <= 0:
        return {'sire': None, 'dam': None}
    
    pedigree = parse_pedigree_table(soup, pedigree_depth)
    sire_data = None
    dam_data = None
    
    if pedigree.get('sire') and pedigree['sire']['url'] not in processed_urls:
        print(f"RECURSIVE PEDIGREE sire_url: {pedigree['sire']['url']}")
        processed_urls.add(pedigree['sire']['url'])
        sire_html = await fetch_dog_page_by_url(session, f"{pedigree['sire']['url']}&gen={gen_param}")
        sire_soup = BeautifulSoup(sire_html, 'lxml')
        sire_info = await parse_dog_info(session, sire_soup, pedigree['sire']['uuid'])
        
        sire_litters = parse_offspring_table(sire_soup)
        sire_parents = await parse_pedigree_recursive(session, sire_soup, processed_urls, pedigree_depth - 1)
        
        sire_data = {
            'dog_info': sire_info,
            'litters': sire_litters,
            'parents': sire_parents
        }
    
    if pedigree.get('dam') and pedigree['dam']['url'] not in processed_urls:
        print(f"RECURSIVE PEDIGREE dam_url: {pedigree['dam']['url']}")
        processed_urls.add(pedigree['dam']['url'])
        dam_html = await fetch_dog_page_by_url(session, f"{pedigree['dam']['url']}&gen={gen_param}")
        dam_soup = BeautifulSoup(dam_html, 'lxml')
        dam_info = await parse_dog_info(session, dam_soup, pedigree['dam']['uuid'])
        
        dam_litters = parse_offspring_table(dam_soup)
        dam_parents = await parse_pedigree_recursive(session, dam_soup, processed_urls, pedigree_depth - 1)
        
        dam_data = {
            'dog_info': dam_info,
            'litters': dam_litters,
            'parents': dam_parents
        }
    
    result = {
        'sire': sire_data, 
        'dam': dam_data,
        'sire_uuid': pedigree.get('sire_uuid'),
        'sire_name': pedigree.get('sire_name'),
        'dam_uuid': pedigree.get('dam_uuid'),
        'dam_name': pedigree.get('dam_name')
    }
    return result

async def parse_dog_page_recursive(session: AsyncClient, html: str, dog_id: str, processed_urls: set = None, recursive: bool = False, pedigree_depth: int = 3) -> Dict:
    if processed_urls is None:
        processed_urls = set()
    
    soup = BeautifulSoup(html, 'lxml')
    dog_info = await parse_dog_info(session, soup, dog_id)
    print(f"Dog info: {dog_info}")
    
    litters = []
    pedigree = {'sire': None, 'dam': None}
    
    if recursive:
        pedigree = await parse_pedigree_recursive(session, soup, processed_urls, pedigree_depth)
        litters = parse_offspring_table(soup)
        print(f"Pedigree: {pedigree}")
        print(f"Litters: {litters}")
    
    parsed_data = {
        'dog_info': dog_info,
        'pedigree': pedigree,
        'litters': litters
    }
    return map_to_dog_model(parsed_data, max_depth=pedigree_depth)

async def process_single_huskypedigree_dog(dog_id: str, recursive: bool = True, pedigree_depth: int = 3):
    class DateTimeEncoder(json.JSONEncoder):
        from datetime import datetime, date
        def default(self, obj):
            if isinstance(obj, (self.datetime, self.date)):
                return obj.isoformat()
            return super().default(obj)
        
    async with AsyncClient() as client:
        html = await fetch_dog_page(client, dog_id)
        result = await parse_dog_page_recursive(client, html, dog_id, recursive=recursive, pedigree_depth=pedigree_depth)
        json_path = f"huskypedigree_{dog_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        async with session_scope() as session:
            saved_dog = await save_to_database(result, session)
        return saved_dog, json_path

async def process_huskypedigree_dogs(dog_ids: List[str], recursive: bool = True, pedigree_depth: int = 3):
    parsed_dog_ids = []
    
    for dog_id in dog_ids:
        try:
            saved_dog, json_path = await process_single_huskypedigree_dog(dog_id, recursive, pedigree_depth)
            if saved_dog and hasattr(saved_dog, 'id'):
                parsed_dog_ids.append(saved_dog.id)
                print(f"Successfully processed dog {dog_id}, saved with ID: {saved_dog.id}")
            else:
                print(f"Failed to save dog {dog_id}")
        except Exception as e:
            logger.error(f"Error processing dog {dog_id}: {str(e)}")
            continue
    
    return {"parsed_dog_ids": parsed_dog_ids, "processed_dogs_count": len(parsed_dog_ids)}

async def parse_dog_list_page(session: AsyncClient, url: str, processed_urls: set = None, recursive: bool = False, pedigree_depth: int = 3, start_page: int = 1, max_pages: int = 10) -> List[Dict]:
    if processed_urls is None:
        processed_urls = set()
    
    result_data = []
    
    try:
        response = await session.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        rows = soup.find_all('tr')
        if not rows:
            logger.warning(f"No table rows found on page: {url}")
            return result_data
        
        data_rows = [row for row in rows if 'legenda' not in row.get('class', [])]
        
        for row in data_rows:
            cells = row.find_all('td')
            if len(cells) < 11:
                continue
            
            # Извлекаем ссылку на собаку из третьей колонки (name)
            name_cell = cells[2] if len(cells) > 2 else None
            if not name_cell:
                continue
            
            name_link = name_cell.find('a', href=True)
            if not name_link:
                continue
            
            # Извлекаем ID собаки из href
            href = name_link['href']
            match = re.search(r'id=(\d+)', href)
            if not match:
                continue
            
            dog_id = match.group(1)
            dog_name = name_link.get_text(strip=True)
            
            # Фильтруем записи без достаточной информации
            if not dog_name or dog_name == "":
                continue
            
            if dog_id not in processed_urls:
                processed_urls.add(dog_id)
                logger.info(f"Processing dog from list: {dog_name} (ID: {dog_id})")
                
                try:
                    # Используем process_single_huskypedigree_dog для полной обработки собаки
                    saved_dog, json_path = await process_single_huskypedigree_dog(
                        dog_id=dog_id,
                        recursive=recursive,
                        pedigree_depth=pedigree_depth
                    )
                    
                    if saved_dog:
                        # Добавляем информацию о сохраненной собаке
                        result_data.append({
                            'dog_id': dog_id,
                            'dog_name': dog_name,
                            'saved_dog_id': saved_dog.id,
                            'json_path': json_path,
                            'status': 'success'
                        })
                        logger.info(f"Successfully processed and saved dog {dog_name} with ID: {saved_dog.id}")
                    else:
                        result_data.append({
                            'dog_id': dog_id,
                            'dog_name': dog_name,
                            'status': 'failed',
                            'error': 'Failed to save dog'
                        })
                        logger.warning(f"Failed to save dog {dog_name} (ID: {dog_id})")
                        
                except Exception as e:
                    result_data.append({
                        'dog_id': dog_id,
                        'dog_name': dog_name,
                        'status': 'error',
                        'error': str(e)
                    })
                    logger.error(f"Error processing dog {dog_id}: {str(e)}")
                    continue
        
        # Проверяем наличие следующей страницы
        next_page_link = soup.find('a', string='next')
        if next_page_link and 'href' in next_page_link.attrs and max_pages > 1:
            next_url = f"{HUSKY_PEDIGREE_NET_API}/{next_page_link['href']}"
            if next_url not in processed_urls:
                processed_urls.add(next_url)
                logger.info(f"Moving to next page: {next_url}")
                next_page_data = await parse_dog_list_page(session, next_url, processed_urls, recursive, pedigree_depth, start_page, max_pages - 1)
                result_data.extend(next_page_data)
        
    except Exception as e:
        logger.error(f"Error parsing dog list page {url}: {str(e)}")
    
    return result_data

async def process_huskypedigree_list(start_page: int = 1, max_pages: int = 5, recursive: bool = True, pedigree_depth: int = 3):
    parsed_dog_ids = []
    failed_dogs = []
    
    # URL для списка собак
    list_url = f"{HUSKY_PEDIGREE_NET_API}/lista.php?pasmina=&adv=1&ime=&otac=&majka=&regbr=&god1=&god2=&hruzg=1&uvoz=1&stranci=1&sl=1&x=50&y=12&str={start_page}"
    
    async with AsyncClient() as http_session:
        try:
            search_data = await parse_dog_list_page(http_session, list_url, recursive=recursive, pedigree_depth=pedigree_depth, start_page=start_page, max_pages=max_pages)
            
            # Обрабатываем результаты
            for dog_result in search_data:
                if dog_result['status'] == 'success':
                    parsed_dog_ids.append(dog_result['saved_dog_id'])
                    logger.info(f"Successfully saved dog {dog_result['dog_name']} with ID: {dog_result['saved_dog_id']}")
                else:
                    failed_dogs.append({
                        'dog_id': dog_result['dog_id'],
                        'dog_name': dog_result['dog_name'],
                        'error': dog_result.get('error', 'Unknown error')
                    })
                    logger.warning(f"Failed to save dog {dog_result['dog_name']}: {dog_result.get('error', 'Unknown error')}")
                        
        except Exception as e:
            logger.error(f"Error processing dog list: {str(e)}")
    
    return {
        "parsed_dog_ids": parsed_dog_ids, 
        "processed_dogs_count": len(parsed_dog_ids),
        "failed_dogs": failed_dogs,
        "total_attempted": len(parsed_dog_ids) + len(failed_dogs)
    }
