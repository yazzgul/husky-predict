from typing import Optional, List, Dict, Tuple, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.dog import Dog
from utils.levenshtein import is_similar_name, normalized_levenshtein_similarity
from datetime import datetime, date


from typing import Dict, Optional, Tuple, List
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

async def find_existing_dog(
        session: AsyncSession,
        dog_data: Dict,
        source: str,
        name_similarity_threshold: float = 0.8,
        parent_similarity_threshold: float = 0.7,
        max_candidates: int = 120,
) -> Tuple[Optional["Dog"], str, float]:
    """
    Поиск существующей собаки:
    1) exact name
    2) birth + exact parents
    3) кандидаты через SQL (ILIKE по токенам) -> Левенштейн по кандидатам
    ВАЖНО: uuid-first НЕ используем для source == "zooportal.pro" (чтобы не матчить только zooportal-uuid).
    Также можно включить поиск по land_of_birth (у тебя поле Dog.land_of_birth).
    """

    registered_name = (dog_data.get("registered_name") or "").strip()
    uuid = dog_data.get("uuid")
    date_of_birth = dog_data.get("date_of_birth")
    sire_name = (dog_data.get("sire_name") or "").strip() or None
    dam_name = (dog_data.get("dam_name") or "").strip() or None
    land_of_birth = (dog_data.get("land_of_birth") or "").strip() or None

    # 1) UUID — используем только НЕ для Zooportal, если тебе это нужно
    # (иначе zooportal будет матчиться "сам на себя" и не будет пытаться склеиться с BA)
    if uuid and source != "zooportal.pro":
        q = select(Dog).where(Dog.uuid == uuid)
        res = await session.execute(q)
        d = res.scalars().first()
        if d:
            return d, "uuid", 1.0

    # 2) Нет имени -> не ищем
    if not registered_name:
        return None, "no_name", 0.0

    # 3) Exact name (+ optional filters)
    q = select(Dog).where(Dog.registered_name == registered_name)
    if date_of_birth is not None:
        q = q.where(Dog.date_of_birth == date_of_birth)
    if land_of_birth:
        q = q.where(Dog.land_of_birth == land_of_birth)

    res = await session.execute(q)
    d = res.scalars().first()
    if d:
        return d, "exact_name", 1.0

    # 4) Date + exact parents (+ optional land)
    if date_of_birth is not None and (sire_name or dam_name):
        q = select(Dog).where(Dog.date_of_birth == date_of_birth)
        if sire_name:
            q = q.where(Dog.sire_name == sire_name)
        if dam_name:
            q = q.where(Dog.dam_name == dam_name)
        if land_of_birth:
            q = q.where(Dog.land_of_birth == land_of_birth)

        res = await session.execute(q)
        d = res.scalars().first()
        if d:
            return d, "birth_parents_exact", 1.0

    # 5) Левенштейн по кандидатам (НЕ по всей таблице)
    name_norm = registered_name.lower()
    tokens = [t for t in name_norm.split() if len(t) >= 3][:6]
    if not tokens:
        tokens = [name_norm[:4]] if len(name_norm) >= 4 else [name_norm]

    like_clauses = [Dog.registered_name.ilike(f"%{t}%") for t in tokens]

    q = select(Dog).where(
        Dog.registered_name.isnot(None),
        or_(*like_clauses),
    )

    # сузим кандидатов по DOB/land, если есть (ускорение и меньше ложных совпадений)
    if date_of_birth is not None:
        q = q.where(Dog.date_of_birth == date_of_birth)
    if land_of_birth:
        q = q.where(Dog.land_of_birth == land_of_birth)

    res = await session.execute(q.limit(max_candidates))
    candidates: List[Dog] = list(res.scalars().all())

    # если слишком строго (0 кандидатов) — ослабим (только по имени)
    if not candidates:
        q2 = select(Dog).where(
            Dog.registered_name.isnot(None),
            or_(*like_clauses),
        )
        res2 = await session.execute(q2.limit(max_candidates))
        candidates = list(res2.scalars().all())

    if not candidates:
        return None, "no_candidates", 0.0

    best_match: Optional[Dog] = None
    best_score: float = 0.0

    for cand in candidates:
        cand_name = (cand.registered_name or "").strip()
        if not cand_name:
            continue

        score = normalized_levenshtein_similarity(
            registered_name.lower().strip(),
            cand_name.lower().strip(),
        )

        if score < name_similarity_threshold:
            continue

        # бонус за точное совпадение даты рождения
        if date_of_birth is not None and getattr(cand, "date_of_birth", None) is not None:
            if cand.date_of_birth == date_of_birth:
                score += 0.10

        # бонусы за родителей
        if sire_name and getattr(cand, "sire_name", None):
            if is_similar_name(sire_name, cand.sire_name, parent_similarity_threshold):
                score += 0.05
        if dam_name and getattr(cand, "dam_name", None):
            if is_similar_name(dam_name, cand.dam_name, parent_similarity_threshold):
                score += 0.05

        # бонус за страну рождения
        if land_of_birth and getattr(cand, "land_of_birth", None):
            if (cand.land_of_birth or "").strip().lower() == land_of_birth.lower():
                score += 0.05

        if score > best_score:
            best_score = score
            best_match = cand

    if best_match:
        return best_match, "levenshtein_candidates", float(best_score)

    return None, "not_found", 0.0

# async def find_existing_dog(
#         session: AsyncSession,
#         dog_data: Dict,
#         source: str,
#         name_similarity_threshold: float = 0.8
# ) -> Tuple[Optional[Dog], str, float]:
#     registered_name = dog_data.get('registered_name')
#     uuid = dog_data.get('uuid')
#     date_of_birth = dog_data.get('date_of_birth')
#     sire_name = dog_data.get('sire_name')
#     dam_name = dog_data.get('dam_name')
#
#     # 1. ВСЕГДА сначала ищем по UUID
#     if uuid:
#         query = select(Dog).where(Dog.uuid == uuid)
#         result = await session.execute(query)
#         existing_dog = result.scalars().first()
#
#         if existing_dog:
#             return existing_dog, "uuid", 1.0
#
#     # 2. Если нет имени, сразу возвращаем None
#     if not registered_name or registered_name.strip() == "":
#         return None, "no_name", 0.0
#
#     # 3. Строгое сравнение по имени
#     query = select(Dog).where(Dog.registered_name == registered_name)
#     result = await session.execute(query)
#     existing_dog = result.scalars().first()
#
#     if existing_dog:
#         return existing_dog, "exact_name", 1.0
#
#     # 4. Поиск по дате рождения + родители
#     if date_of_birth and (sire_name or dam_name):
#         query = select(Dog).where(Dog.date_of_birth == date_of_birth)
#
#         if sire_name:
#             query = query.where(Dog.sire_name == sire_name)
#         if dam_name:
#             query = query.where(Dog.dam_name == dam_name)
#
#         result = await session.execute(query)
#         existing_dog = result.scalars().first()
#
#         if existing_dog:
#             return existing_dog, "birth_parents", 1.0
#
#     # 5. Поиск по алгоритму Левенштейна (только если есть имя)
#     if registered_name:
#         all_dogs_query = select(Dog).where(Dog.registered_name.isnot(None))
#         result = await session.execute(all_dogs_query)
#         all_dogs = result.scalars().all()
#
#         best_match = None
#         best_similarity = 0.0
#
#         for dog in all_dogs:
#             if dog.registered_name:
#                 similarity = normalized_levenshtein_similarity(
#                     registered_name.lower().strip(),
#                     dog.registered_name.lower().strip()
#                 )
#
#                 if similarity > best_similarity and similarity >= name_similarity_threshold:
#                     if date_of_birth and dog.date_of_birth:
#                         if date_of_birth == dog.date_of_birth:
#                             similarity += 0.1
#
#                     if sire_name and dog.sire_name:
#                         if is_similar_name(sire_name, dog.sire_name, 0.7):
#                             similarity += 0.05
#
#                     if dam_name and dog.dam_name:
#                         if is_similar_name(dam_name, dog.dam_name, 0.7):
#                             similarity += 0.05
#
#                     if similarity > best_similarity:
#                         best_similarity = similarity
#                         best_match = dog
#
#         if best_match:
#             return best_match, "levenshtein", best_similarity
#
#     return None, "not_found", 0.0

def detect_conflicts(existing_dog: Dog, new_data: Dict, source: str) -> Tuple[bool, Dict]:
    conflicts = {}
    has_conflicts = False

    fields_to_check = [
        'registered_name', 'call_name', 'sex', 'date_of_birth', 'date_of_death',
        'land_of_birth', 'land_of_standing', 'size', 'weight', 'color',
        'eyes_color', 'registration_number', 'brand_chip', 'coi', 'photo_url',
        'kennel', 'notes', 'sire_name', 'dam_name', 'zooportal_id'
    ]

    for field in fields_to_check:
        existing_value = getattr(existing_dog, field, None)
        new_value = new_data.get(field)

        # Преобразуем числовые поля
        existing_value = _convert_numeric_field(field, existing_value)
        new_value = _convert_numeric_field(field, new_value)

        # Пропускаем пустые значения
        if new_value is None or new_value == "":
            continue

        # Если поле пустое в существующей записи, заполняем его
        if existing_value is None or existing_value == "":
            continue

        if field == 'registered_name':
            if isinstance(existing_value, str) and isinstance(new_value, str):
                if existing_value.upper() == new_value.upper():
                    continue  # Это одно и то же имя, только регистр разный

        # Если значения отличаются, создаем конфликт
        if existing_value != new_value:
            if field not in conflicts:
                conflicts[field] = {}

            # Преобразуем значения для JSON сериализации
            def prepare_value(v):
                if isinstance(v, (datetime, date)):
                    return v.isoformat()
                return v

            existing_source = existing_dog.source or "unknown"
            conflicts[field][existing_source] = prepare_value(existing_value)
            conflicts[field][source] = prepare_value(new_value)

            has_conflicts = True

    return has_conflicts, conflicts

def detect_dict_conflicts(
    left: Dict[str, Any],
    right: Dict[str, Any],
    left_source: str,
    right_source: str,
) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """
    Детект конфликтов между ДВУМЯ словарями.
    Конфликт = оба значения есть, не пустые и !=
    """
    conflicts: Dict[str, Dict[str, Any]] = {}
    has_conflicts = False

    common_keys = set(left.keys()) & set(right.keys())

    for key in common_keys:
        lv = left.get(key)
        rv = right.get(key)

        if lv in (None, "") or rv in (None, ""):
            continue

        # datetime/date → iso
        def prep(v):
            if isinstance(v, (datetime, date)):
                return v.isoformat()
            return v

        if lv != rv:
            conflicts[key] = {
                left_source: prep(lv),
                right_source: prep(rv),
            }
            has_conflicts = True

    return has_conflicts, conflicts


def merge_dog_data(existing_dog: Dog, new_data: Dict, source: str) -> Tuple[bool, Dict]:
    has_changes = False
    has_conflicts, conflicts = detect_conflicts(existing_dog, new_data, source)

    fields_to_update = [
        'registered_name', 'call_name', 'sex', 'date_of_birth', 'date_of_death',
        'land_of_birth', 'land_of_standing', 'size', 'weight', 'color',
        'eyes_color', 'registration_number', 'brand_chip', 'coi', 'photo_url',
        'kennel', 'notes', 'sire_name', 'dam_name', 'sire_uuid', 'dam_uuid'
    ]

    for field in fields_to_update:
        existing_value = getattr(existing_dog, field, None)
        new_value = new_data.get(field)

        # Преобразуем новое значение к нужному типу
        new_value = _convert_field(field, new_value)

        # Пропускаем пустые значения
        if new_value is None or new_value == "":
            continue

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

def _convert_numeric_field(field: str, value: Any) -> Any:
    """Преобразует строки в числа для числовых полей"""
    if field in ['size', 'weight', 'coi']:
        if isinstance(value, str):
            try:
                return float(value.strip())
            except (ValueError, TypeError, AttributeError):
                return value
    return value


def _convert_field(field: str, value: Any) -> Any:
    """Преобразует строки в соответствующие типы для полей"""
    if value is None:
        return value

    # Поля дат
    if field in ['date_of_birth', 'date_of_death', 'modified_at', 'coi_updated_on']:
        if isinstance(value, str):
            # Используем parse_datetime из parser_utils
            from utils.parser_utils import parse_datetime
            return parse_datetime(value)

    # Числовые поля
    if field in ['size', 'weight', 'coi']:
        if isinstance(value, str):
            try:
                clean = value.strip()
                if clean in ["", " ", "nan", "NaN", "null", "None"]:
                    return None
                return float(clean)
            except (ValueError, TypeError):
                return value

    return value