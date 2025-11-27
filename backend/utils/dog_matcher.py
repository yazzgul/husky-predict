from typing import Optional, List, Dict, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.dog import Dog
from utils.levenshtein import is_similar_name, normalized_levenshtein_similarity

async def find_existing_dog(
    session: AsyncSession,
    dog_data: Dict,
    source: str,
    name_similarity_threshold: float = 0.8
) -> Tuple[Optional[Dog], str, float]:

    registered_name = dog_data.get('registered_name')
    uuid = dog_data.get('uuid')
    date_of_birth = dog_data.get('date_of_birth')
    sire_name = dog_data.get('sire_name')
    dam_name = dog_data.get('dam_name')
    
    if not registered_name:
        return None, "no_name", 0.0
    
    # 1. Строгое сравнение по имени
    query = select(Dog).where(Dog.registered_name == registered_name)
    result = await session.execute(query)
    existing_dog = result.scalars().first()
    
    if existing_dog:
        return existing_dog, "exact_name", 1.0
    
    # 2. Поиск по UUID
    if uuid:
        query = select(Dog).where(Dog.uuid == uuid)
        result = await session.execute(query)
        existing_dog = result.scalars().first()
        
        if existing_dog:
            return existing_dog, "uuid", 1.0
    
    # 3. Поиск по дате рождения + родители
    if date_of_birth and (sire_name or dam_name):
        query = select(Dog).where(Dog.date_of_birth == date_of_birth)
        
        if sire_name:
            query = query.where(Dog.sire_name == sire_name)
        if dam_name:
            query = query.where(Dog.dam_name == dam_name)
        
        result = await session.execute(query)
        existing_dog = result.scalars().first()
        
        if existing_dog:
            return existing_dog, "birth_parents", 1.0
    
    # 4. Поиск по алгоритму Левенштейна
    if registered_name:
        # Получаем всех собак с похожими именами
        all_dogs_query = select(Dog).where(Dog.registered_name.isnot(None))
        result = await session.execute(all_dogs_query)
        all_dogs = result.scalars().all()
        
        best_match = None
        best_similarity = 0.0
        
        for dog in all_dogs:
            if dog.registered_name:
                similarity = normalized_levenshtein_similarity(
                    registered_name.lower().strip(),
                    dog.registered_name.lower().strip()
                )
                
                if similarity > best_similarity and similarity >= name_similarity_threshold:
                    # Дополнительная проверка по дате рождения и родителям
                    if date_of_birth and dog.date_of_birth:
                        if date_of_birth == dog.date_of_birth:
                            similarity += 0.1  # Бонус за совпадение даты
                    
                    if sire_name and dog.sire_name:
                        if is_similar_name(sire_name, dog.sire_name, 0.7):
                            similarity += 0.05  # Бонус за совпадение отца
                    
                    if dam_name and dog.dam_name:
                        if is_similar_name(dam_name, dog.dam_name, 0.7):
                            similarity += 0.05  # Бонус за совпадение матери
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = dog
        
        if best_match:
            return best_match, "levenshtein", best_similarity
    
    return None, "not_found", 0.0

def detect_conflicts(existing_dog: Dog, new_data: Dict, source: str) -> Tuple[bool, Dict]:

    conflicts = {}
    has_conflicts = False
    
    # Список полей для проверки конфликтов
    fields_to_check = [
        'registered_name', 'call_name', 'sex', 'date_of_birth', 'date_of_death',
        'land_of_birth', 'land_of_standing', 'size', 'weight', 'color', 
        'eyes_color', 'registration_number', 'brand_chip', 'coi', 'photo_url',
        'kennel', 'notes', 'sire_name', 'dam_name'
    ]
    
    for field in fields_to_check:
        existing_value = getattr(existing_dog, field, None)
        new_value = new_data.get(field)
        
        # Пропускаем пустые значения
        if new_value is None or new_value == "":
            continue
        
        # Если поле пустое в существующей записи, заполняем его
        if existing_value is None or existing_value == "":
            continue
        
        # Если значения отличаются, создаем конфликт
        if existing_value != new_value:
            if field not in conflicts:
                conflicts[field] = {}
            
            # Добавляем существующее значение с источником
            existing_source = existing_dog.source or "unknown"
            conflicts[field][existing_source] = existing_value
            
            # Добавляем новое значение с источником
            conflicts[field][source] = new_value
            
            has_conflicts = True
    
    return has_conflicts, conflicts

def merge_dog_data(existing_dog: Dog, new_data: Dict, source: str) -> Tuple[bool, Dict]:

    has_changes = False
    has_conflicts, conflicts = detect_conflicts(existing_dog, new_data, source)
    
    # Список полей для обновления (только если они пустые в существующей записи)
    fields_to_update = [
        'registered_name', 'call_name', 'sex', 'date_of_birth', 'date_of_death',
        'land_of_birth', 'land_of_standing', 'size', 'weight', 'color', 
        'eyes_color', 'registration_number', 'brand_chip', 'coi', 'photo_url',
        'kennel', 'notes', 'sire_name', 'dam_name', 'sire_uuid', 'dam_uuid'
    ]
    
    for field in fields_to_update:
        existing_value = getattr(existing_dog, field, None)
        new_value = new_data.get(field)
        
        # Обновляем только если поле пустое в существующей записи
        if (existing_value is None or existing_value == "" or existing_value == 0) and new_value is not None:
            setattr(existing_dog, field, new_value)
            has_changes = True
    
    # Обновляем информацию о конфликтах
    if has_conflicts:
        existing_dog.has_conflicts = True
        if existing_dog.conflicts is None:
            existing_dog.conflicts = {}
        
        # Объединяем существующие конфликты с новыми
        for field, field_conflicts in conflicts.items():
            if field not in existing_dog.conflicts:
                existing_dog.conflicts[field] = {}
            existing_dog.conflicts[field].update(field_conflicts)
        
        has_changes = True
    
    return has_changes, conflicts 