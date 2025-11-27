from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from pathlib import Path
import re
import logging
import json
import sys

from models.dog import Dog, DogSiblingLink
from models.people import Breeder, Owner
from models.litters import Litter
from models.associations import DogBreederLink, DogOwnerLink
from core.parsersConfig import BREEDBASE_API, BREEDBASE_DOG_PATH
from core.database import session_scope
from utils.dog_matcher import find_existing_dog, detect_conflicts, merge_dog_data

root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

logger = logging.getLogger(__name__)

dog_page_url = f"{BREEDBASE_API}{BREEDBASE_DOG_PATH}/"
ROWS_PER_PAGE = 50

async def fetch_dog_page(session: AsyncClient, dog_name: str) -> str:
    url = f"{dog_page_url}details.php?name={dog_name}&gens=6"
    response = await session.get(url)
    response.raise_for_status()
    return response.text

async def fetch_dog_page_by_url(session: AsyncClient, url: str) -> str:
    response = await session.get(url)
    response.raise_for_status()
    
    return response.text

def generate_uuid_from_url(url: str) -> str:
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()
def generate_uuid_from_name(name: str) -> str:
    import hashlib
    return hashlib.md5(name.encode()).hexdigest()

def parse_dog_info(soup: BeautifulSoup) -> Dict:
    info = {}
    title_div = soup.find('div', class_='titlename')
    if title_div:
        name_tag = title_div.find('h1', itemprop='name')
        if name_tag:
            info['name'] = name_tag.get_text(strip=True)
    awards_div = soup.find('div', itemprop='awards')
    if awards_div:
        info['awards'] = awards_div.get_text(strip=True)
    general_info_div = soup.find('div', class_='generalInfo')
    if general_info_div:
        for row in general_info_div.find_all('div', class_='textRow'):
            label = row.find('div', class_='textLabel')
            description = row.find('div', class_='textDescription')
            if label and description:
                key = label.get_text(strip=True).lower().rstrip(':')
                value = description.get_text(strip=True)
                info[key] = value
                # Извлечение ссылок для полей заводчик, владелец, отец, мать
                links = description.find_all('a', href=True)
                if links:
                    if key == 'владелец':
                        info[f"{key}_names"] = [link.get_text(strip=True) for link in links]
                        info[f"{key}_urls"] = [f"{dog_page_url}{link['href']}" if not link['href'].startswith('http') else link['href'] for link in links]
                    else:
                        link = links[0]
                        relative_url = link['href']
                        full_url = f"{dog_page_url}{relative_url}" if not relative_url.startswith('http') else relative_url
                        info[f"{key}_url"] = full_url
    return info

def parse_dog_page(html: str, processed_urls: set = None) -> Dict:
    if processed_urls is None:
        processed_urls = set()
    soup = BeautifulSoup(html, 'lxml')
    dog_info = parse_dog_info(soup)
    return {
        'dog_info': dog_info
    }

async def save_to_database(dog_data: Dict, session: AsyncSession) -> Optional[int]:
    try:
        existing_dog, match_method, similarity = await find_existing_dog(
            session, dog_data, "breedbase.ru"
        )
        
        if existing_dog:
            logger.info(f"Found existing dog by {match_method} (similarity: {similarity:.2f}): {existing_dog.registered_name}")
            
            has_conflicts, conflicts = detect_conflicts(existing_dog, dog_data, "breedbase.ru")
            
            if has_conflicts:
                logger.warning(f"Conflicts detected for dog {existing_dog.registered_name}: {conflicts}")
                existing_dog.has_conflicts = True
                if existing_dog.conflicts is None:
                    existing_dog.conflicts = {}
                
                for field, field_conflicts in conflicts.items():
                    if field not in existing_dog.conflicts:
                        existing_dog.conflicts[field] = {}
                    existing_dog.conflicts[field].update(field_conflicts)
            
            has_changes, _ = merge_dog_data(existing_dog, dog_data, "breedbase.ru")
            
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

        async def handle_siblings(siblings_data: List[Dict], dog_id: int):
            for sibling_data in siblings_data:
                existing_sibling, _, _ = await find_existing_dog(session, sibling_data, "breedbase.ru")
                if existing_sibling:
                    sibling = existing_sibling
                else:
                    sibling = Dog(**{k: v for k, v in sibling_data.items() if k not in ['breeders', 'owners', 'siblings', 'litters', 'sire', 'dam']})
                    session.add(sibling)
                    await session.flush()
                    await session.refresh(sibling)
                await session.execute(delete(DogSiblingLink).where(DogSiblingLink.dog_id == dog_id, DogSiblingLink.sibling_id == sibling.id))
                session.add(DogSiblingLink(dog_id=dog_id, sibling_id=sibling.id))
            await session.flush()

        async def handle_litters(litters_data: List[Dict], dog_id: int, is_sire: bool = False, is_dam: bool = False):
            print(f"Litters data: {litters_data}")
            litter_groups = {}
            for litter_data in litters_data:
                date_of_birth = litter_data.get('date_of_birth')
                if date_of_birth:
                    if date_of_birth not in litter_groups:
                        litter_groups[date_of_birth] = []
                    litter_groups[date_of_birth].append(litter_data)
            print(f"Litter groups: {litter_groups}")
            
            for date_of_birth, group in litter_groups.items():
                litter_data = group[0]
                puppies = litter_data.pop('puppies', [])
                litter = Litter(**litter_data)
                
                if is_sire:
                    litter.sire_id = dog_id
                if is_dam:
                    litter.dam_id = dog_id

                if puppies and not (is_sire or is_dam):
                    for puppy_data in puppies:
                        if 'sire' in puppy_data:
                            sire = await save_to_database(puppy_data['sire'], session)
                            if sire:
                                litter.sire_id = sire.id
                        if 'dam' in puppy_data:
                            dam = await save_to_database(puppy_data['dam'], session)
                            if dam:
                                litter.dam_id = dam.id
                        break

                session.add(litter)
                await session.flush()
                await session.refresh(litter)
                
                for puppy_data in puppies:
                    existing_puppy, _, _ = await find_existing_dog(session, puppy_data, "breedbase.ru")
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
            
        if dog_data.get('dam'):
            dam = await save_to_database(dog_data['dam'], session)
            if dam:
                dog.dam_id = dam.id

        if dog_data.get('breeders'):
            await handle_breeders(dog_data['breeders'], dog.id)
        if dog_data.get('owners'):
            await handle_owners(dog_data['owners'], dog.id)
        
        if dog_data.get('siblings'):
            await handle_siblings(dog_data['siblings'], dog.id)
        
        if dog_data.get('litters'):
            await handle_litters(dog_data['litters'], dog.id, is_sire=(dog.sex == 1), is_dam=(dog.sex == 2))

        await session.commit()
        return dog
    except Exception as e:
        logger.error(f"Error saving to database: {str(e)}")
        await session.rollback()
        return None

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        russian_months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
            'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        parts = date_str.split()
        if len(parts) == 3:
            day = int(parts[0])
            month_str = parts[1].lower()
            year = int(parts[2])
            month = russian_months.get(month_str)
            if month:
                return datetime(year, month, day)
        return None
    except (ValueError, KeyError) as e:
        logger.warning(f"Could not parse date: {date_str}, error: {str(e)}")
        return None

def parse_float(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

async def parse_related_dogs_recursive(session: AsyncClient, soup: BeautifulSoup, section_class: str, processed_urls: set) -> List[Dict]:
    related_dogs = []
    section_div = soup.find('div', class_=section_class)
    if section_div:
        for link in section_div.find_all('a', href=True):
            relative_url = link['href']
            full_url = f"{dog_page_url}{relative_url}" if not relative_url.startswith('http') else relative_url
            if full_url not in processed_urls:
                processed_urls.add(full_url)
                name = link.get_text(strip=True)
                dog_html = await fetch_dog_page_by_url(session, full_url)
                dog_data = parse_dog_page(dog_html, processed_urls)
                related_dogs.append({
                    'name': name,
                    'url': full_url,
                    'data': dog_data
                })
                
    return related_dogs

async def parse_pedigree_recursive(session: AsyncClient, soup: BeautifulSoup, processed_urls: set, pedigree_depth: int = 5) -> Dict:
    if pedigree_depth <= 0:
        return {'sire': None, 'dam': None}
    
    dog_info = parse_dog_info(soup)
    print(f"RECURSIVE PEDIGREE dog_info: {dog_info}")
    sire_data = None
    dam_data = None
    
    if 'отец_url' in dog_info and dog_info['отец_url'] not in processed_urls:
        print(f"RECURSIVE PEDIGREE sire_url: {dog_info['отец_url']}")
        processed_urls.add(dog_info['отец_url'])
        sire_html = await fetch_dog_page_by_url(session, dog_info['отец_url'])
        sire_info = parse_dog_info(BeautifulSoup(sire_html, 'lxml'))
        sire_data = {
            'dog_info': sire_info,
            'parents': await parse_pedigree_recursive(session, BeautifulSoup(sire_html, 'lxml'), processed_urls, pedigree_depth - 1)
        }
    
    if 'мать_url' in dog_info and dog_info['мать_url'] not in processed_urls:
        print(f"RECURSIVE PEDIGREE dam_url: {dog_info['мать_url']}")
        processed_urls.add(dog_info['мать_url'])
        dam_html = await fetch_dog_page_by_url(session, dog_info['мать_url'])
        dam_info = parse_dog_info(BeautifulSoup(dam_html, 'lxml'))
        dam_data = {
            'dog_info': dam_info,
            'parents': await parse_pedigree_recursive(session, BeautifulSoup(dam_html, 'lxml'), processed_urls, pedigree_depth - 1)
        }
    result = {'sire': sire_data, 'dam': dam_data}
    
    # print(f"RECURSIVE PEDIGREE pedigree: {result}")
    return result

def map_to_dog_model(parsed_data: Dict, depth: int = 0, max_depth: int = 5) -> Dict:
    dog_info = parsed_data.get('dog_info', {})
    siblings = parsed_data.get('siblings', [])
    children = parsed_data.get('children', [])
    pedigree = parsed_data.get('pedigree', {})

    sire_link_name = None
    dam_link_name = None
    
    if 'отец_url' in dog_info:
        sire_url = dog_info['отец_url']
        sire_link_name = sire_url.split('name=')[-1] if 'name=' in sire_url else None
    if 'мать_url' in dog_info:
        dam_url = dog_info['мать_url']
        dam_link_name = dam_url.split('name=')[-1] if 'name=' in dam_url else None
    
    if 'url' in dog_info:
        print(f"Link name: {dog_info['url'].split('name=')[-1] if 'name=' in dog_info['url'] else None}")
        dog_info['link_name'] = dog_info['url'].split('name=')[-1] if 'name=' in dog_info['url'] else None
    
    dog_data = {
        'registered_name': dog_info.get('name'),
        'call_name': dog_info.get('домашняя кличка'),
        'sex': 1 if dog_info.get('пол', '').lower() == 'male' else 2,
        'date_of_birth': parse_date(dog_info.get('дата рождения', '')),
        'date_of_death': parse_date(dog_info.get('дата смерти', '')),
        'land_of_birth': dog_info.get('страна рождения'),
        'land_of_standing': dog_info.get('местонахождение'),
        'color': dog_info.get('окрас'),
        'size': parse_float(dog_info.get('рост', '')),
        'weight': parse_float(dog_info.get('вес', '')),
        'other_titles': dog_info.get('титулы'),
        'kennel': dog_info.get('питомник'),
        'distinguishing_features': dog_info.get('отличительные черты'),
        'brand_chip': dog_info.get('клеймо/чип'),
        'sire_name': dog_info.get('отец'),
        'sire_link_name': sire_link_name,
        'dam_name': dog_info.get('мать'),
        'dam_link_name': dam_link_name,
        'source': 'breedbase.ru',
        'uuid': generate_uuid_from_url(dog_info.get('link_name', '')) if 'link_name' in dog_info else generate_uuid_from_name(dog_info.get('name', '')),
    }
    
    # Breeders
    breeder_name = dog_info.get('заводчик')
    if breeder_name:
        dog_data['breeders'] = [{'name': breeder_name, 'is_breeder': True}]
    else:
        dog_data['breeders'] = []
    
    # Owners
    if 'владелец_names' in dog_info and dog_info['владелец_names']:
        dog_data['owners'] = [{'name': name, 'is_main_owner': True} for name in dog_info['владелец_names']]
    elif 'владелец' in dog_info and dog_info['владелец']:
        dog_data['owners'] = [{'name': dog_info['владелец'], 'is_main_owner': True}]
    else:
        dog_data['owners'] = []
    
    if depth < max_depth:
        if pedigree.get('sire') and pedigree['sire'].get('dog_info'):
            dog_data['sire'] = map_to_dog_model({'dog_info': pedigree['sire'].get('dog_info', {}), 'pedigree': pedigree['sire'].get('parents', {})}, depth + 1, max_depth)
        if pedigree.get('dam') and pedigree['dam'].get('dog_info'):
            dog_data['dam'] = map_to_dog_model({'dog_info': pedigree['dam'].get('dog_info', {}), 'pedigree': pedigree['dam'].get('parents', {})}, depth + 1, max_depth)
    
    # Siblings
    dog_data['siblings'] = [map_to_dog_model({'dog_info': sib['data']['dog_info'], 'pedigree': {}}, depth + 1, max_depth) for sib in siblings if 'data' in sib and 'dog_info' in sib['data']]
    
    # Litters (children)
    litter_dict = {}
    for child in children:
        if 'data' in child and 'dog_info' in child['data']:
            child_data = map_to_dog_model({'dog_info': child['data']['dog_info'], 'pedigree': {}}, depth + 1, max_depth)
            dob = child_data.get('date_of_birth')
            if dob:
                if dob not in litter_dict:
                    litter_dict[dob] = {
                        'date_of_birth': dob,
                        'litter_male_count': 0,
                        'litter_female_count': 0,
                        'litter_undef_count': 0,
                        'puppies': []
                    }
                litter_dict[dob]['puppies'].append(child_data)
                if child_data.get('sex') == 1:
                    litter_dict[dob]['litter_male_count'] += 1
                elif child_data.get('sex') == 2:
                    litter_dict[dob]['litter_female_count'] += 1
                else:
                    litter_dict[dob]['litter_undef_count'] += 1
    dog_data['litters'] = list(litter_dict.values())
    
    return dog_data

async def parse_dog_page_recursive(session: AsyncClient, html: str, dog_link_name: str, processed_urls: set = None, recursive: bool = False, pedigree_depth: int = 5) -> Dict:
    if processed_urls is None:
        processed_urls = set()
    
    soup = BeautifulSoup(html, 'lxml')
    dog_info = parse_dog_info(soup)
    print(f"Dog info: {dog_info}")
    dog_info['link_name'] = dog_link_name
    siblings = []
    children = []
    pedigree = {'sire': None, 'dam': None}
    
    if recursive:
        siblings = await parse_related_dogs_recursive(session, soup, 'siblings', processed_urls)
        children = await parse_related_dogs_recursive(session, soup, 'children', processed_urls)
        pedigree = await parse_pedigree_recursive(session, soup, processed_urls, pedigree_depth)
        print(f"Pedigree: {pedigree}")
    parsed_data = {
        'dog_info': dog_info,
        'siblings': siblings,
        'children': children,
        'pedigree': pedigree
    }
    return map_to_dog_model(parsed_data, max_depth=pedigree_depth)

async def parse_search_results(session: AsyncClient, url: str, processed_urls: set = None, recursive: bool = False, pedigree_depth: int = 5, max_pages: int = 10, start_page: int = 0) -> List[Dict]:
    if processed_urls is None:
        processed_urls = set()
    
    result_data = []
    response = await session.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    table = soup.find('table', id='doglist')
    if not table:
        logging.warning(f"No doglist table found on page: {url}")
        return result_data
    
    rows = table.find_all('tr')[1:]
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 6:
            continue
        
        name_cell = cells[0]
        name_link = name_cell.find('a')
        if not name_link or 'href' not in name_link.attrs:
            continue
        name_text = name_link.text.strip()
        dog_link = name_link['href']
        if not dog_link.startswith('http'):
            dog_link = f"{BREEDBASE_API}{BREEDBASE_DOG_PATH}/{dog_link}"
        
        if re.match(r'^[0-9\/?…]+$', name_text):
            continue
        
        sex = cells[1].text.strip()
        sire = cells[2].text.strip()
        dam = cells[3].text.strip()
        birth_date = cells[5].text.strip()
        
        if not birth_date and not sire and not dam:
            continue
        
        if dog_link not in processed_urls:
            processed_urls.add(dog_link)
            logging.info(f"Processing dog from search results: {name_text} - {dog_link}")
            dog_html = await fetch_dog_page_by_url(session, dog_link)
            dog_data = await parse_dog_page_recursive(session, dog_html, dog_link, processed_urls, recursive, pedigree_depth)
            if dog_data:
                result_data.append(dog_data)
    
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    start_value = int(query_params.get('start', ['0'])[-1])
    print(f"Start value: {start_value}")
    next_start = start_value + ROWS_PER_PAGE
    next_page = int(next_start / ROWS_PER_PAGE)
    print(f"next_start: {next_start}")
    query_params['start'] = [str(next_start)]
    print(f"query_params['start']: {query_params['start']}")
    next_url = urlunparse(parsed_url._replace(query=urlencode(query_params, doseq=True)))
    print(f"next_start / {ROWS_PER_PAGE}: {next_start / ROWS_PER_PAGE}")
    print(f"max_pages >= next_start / {ROWS_PER_PAGE}: {max_pages >= (next_start / ROWS_PER_PAGE)}")
    
    if next_url not in processed_urls and max_pages >= next_page:
        page_info = soup.find(text=re.compile(r'Найдено \*\*[0-9]+ собак\*\*'))
        if page_info:
            total_dogs = int(re.search(r'Найдено \*\*([0-9]+) собак\*\*', page_info).group(1))
            if next_start >= total_dogs:
                logging.info(f"Reached or exceeded total dogs ({total_dogs}), stopping pagination.")
                return result_data
        processed_urls.add(next_url)
        logging.info(f"Constructed next search results page URL: {next_url}")
        next_page_data = await parse_search_results(session, next_url, processed_urls, recursive, pedigree_depth, max_pages)
        result_data.extend(next_page_data)
    
    return result_data

async def process_single_breedbase_dog(dog_link_name: str, recursive: bool = True, pedigree_depth: int = 5):
    class DateTimeEncoder(json.JSONEncoder):
        from datetime import datetime, date
        def default(self, obj):
            if isinstance(obj, (self.datetime, self.date)):
                return obj.isoformat()
            return super().default(obj)
        
    async with AsyncClient() as client:
        html = await fetch_dog_page(client, dog_link_name)
        result = await parse_dog_page_recursive(client, html, dog_link_name, recursive=recursive, pedigree_depth=pedigree_depth)
        json_path = f"{dog_link_name.replace('-', '_')}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        async with session_scope() as session:
            saved_dog = await save_to_database(result, session)
        return saved_dog, json_path

async def process_breedbase_pages(pages_count: int = 1, start_page: int = 0, recursive: bool = True, pedigree_depth: int = 5):
    parsed_dog_ids = []
    search_url = f"{BREEDBASE_API}{BREEDBASE_DOG_PATH}/results.php?mode=advanced&name=&nickname=&sex=&byear=&landofbirth=&landofstanding=&color=&kennel=&photos=photos&action=search&start={start_page * ROWS_PER_PAGE}"
    async with AsyncClient() as http_session:
        search_data = await parse_search_results(http_session, search_url, recursive=recursive, pedigree_depth=pedigree_depth, max_pages=pages_count)
        async with session_scope() as db_session:
            for dog_data in search_data:
                saved_dog = await save_to_database(dog_data, db_session)
                if saved_dog and hasattr(saved_dog, 'id'):
                    parsed_dog_ids.append(saved_dog.id)
    return {"parsed_dog_ids": parsed_dog_ids, "processed_dogs_count": len(parsed_dog_ids)}
