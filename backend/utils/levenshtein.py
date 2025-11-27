def levenshtein_distance(str1: str, str2: str) -> int:
    if not str1:
        return len(str2)
    if not str2:
        return len(str1)
    
    # Используем только два ряда для оптимизации памяти
    size1, size2 = len(str1), len(str2)
    
    # Если разница в длине больше максимального расстояния, возвращаем её
    if abs(size1 - size2) > max(size1, size2):
        return max(size1, size2)
    
    # Инициализируем первый ряд
    current_row = list(range(size2 + 1))
    
    for i in range(1, size1 + 1):
        previous_row = current_row
        current_row = [i] + [0] * size2
        
        for j in range(1, size2 + 1):
            if str1[i - 1] == str2[j - 1]:
                current_row[j] = previous_row[j - 1]
            else:
                current_row[j] = min(
                    previous_row[j] + 1,      # удаление
                    current_row[j - 1] + 1,   # вставка
                    previous_row[j - 1] + 1   # замена
                )
    
    return current_row[size2]

def normalized_levenshtein_similarity(str1: str, str2: str) -> float:
    if not str1 and not str2:
        return 1.0
    if not str1 or not str2:
        return 0.0
    
    distance = levenshtein_distance(str1, str2)
    max_len = max(len(str1), len(str2))
    
    return 1.0 - (distance / max_len)

def is_similar_name(name1: str, name2: str, threshold: float = 0.8) -> bool:
    if not name1 or not name2:
        return False
    
    # Нормализуем имена для сравнения
    name1_norm = name1.lower().strip()
    name2_norm = name2.lower().strip()
    
    # Если имена идентичны после нормализации
    if name1_norm == name2_norm:
        return True
    
    # Проверяем сходство
    similarity = normalized_levenshtein_similarity(name1_norm, name2_norm)
    return similarity >= threshold

def find_best_match(target_name: str, candidates: list, threshold: float = 0.8) -> tuple:
    if not target_name or not candidates:
        return None, 0.0
    
    best_match = None
    best_similarity = 0.0
    
    for candidate in candidates:
        candidate_name = candidate.name if hasattr(candidate, 'name') else str(candidate)
        
        if not candidate_name:
            continue
        
        similarity = normalized_levenshtein_similarity(
            target_name.lower().strip(),
            candidate_name.lower().strip()
        )
        
        if similarity > best_similarity and similarity >= threshold:
            best_similarity = similarity
            best_match = candidate
    
    return best_match, best_similarity 