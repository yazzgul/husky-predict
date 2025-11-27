from datetime import datetime
from http.client import HTTPException
import logging
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, Any, Set, Tuple
from collections import defaultdict
import tempfile
import os
from graphviz import Digraph

from models import Dog, Breeder, Owner, Title, Litter
from models.associations import DogBreederLink, DogOwnerLink

logger = logging.getLogger(__name__)

def collect_pedigree(dog, max_depth=5, current_depth=0, collected=None):
    if collected is None:
        collected = {}
    if not dog or current_depth >= max_depth or dog.id in collected:
        return collected
    collected[dog.id] = dog
    if hasattr(dog, 'sire') and dog.sire:
        collect_pedigree(dog.sire, max_depth, current_depth + 1, collected)
    if hasattr(dog, 'dam') and dog.dam:
        collect_pedigree(dog.dam, max_depth, current_depth + 1, collected)
    return collected

def build_pedigree_graph(dog, collected):
    dot = Digraph(comment=f"Pedigree for {dog.registered_name}", format='pdf')
    # Add nodes
    for d in collected.values():
        label = f"{d.registered_name or ''}\nID: {d.id}\nSex: {'M' if d.sex==1 else 'F'}\nBorn: {d.date_of_birth.date() if d.date_of_birth else ''}"
        dot.node(str(d.id), label)
    # Add edges
    for d in collected.values():
        if d.sire_id and d.sire_id in collected:
            dot.edge(str(d.sire_id), str(d.id), label="sire")
        if d.dam_id and d.dam_id in collected:
            dot.edge(str(d.dam_id), str(d.id), label="dam")
    return dot

class DogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dog_by_id(self, dog_id: int) -> Dog:
        result = await self.session.execute(
            select(Dog)
            .where(Dog.id == dog_id)
            .options(
                selectinload(Dog.breeders),
                selectinload(Dog.owners),
                selectinload(Dog.titles),
                selectinload(Dog.litters_as_dam),
                selectinload(Dog.litters_as_sire),
                selectinload(Dog.birth_litter),
                selectinload(Dog.dam),
                selectinload(Dog.sire)
            )
        )
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        return dog

    async def calculate_coi(self, dog_id: int, max_generations: int = 10) -> Dict[str, Any]:
        try:
            dog = await self.get_dog_by_id(dog_id)
            
            if not dog:
                raise HTTPException(status_code=404, detail="Dog not found")
            
            pedigree_tree = await self._build_pedigree_tree(dog, max_generations)
            
            # Calculate COI
            coi_result = self._calculate_coi_from_tree(pedigree_tree)
            
            dog.coi = coi_result['coi']
            dog.coi_updated_on = datetime.now()
            await self.session.commit()
            
            return {
                "dog_id": dog_id,
                "dog_name": dog.registered_name,
                "coi": coi_result['coi'],
                "coi_percentage": coi_result['coi'] * 100,
                "generations_analyzed": coi_result['generations_analyzed'],
                "common_ancestors": coi_result['common_ancestors'],
                "calculation_details": coi_result['details'],
                "updated_at": dog.coi_updated_on
            }
            
        except Exception as e:
            logger.error(f"Error calculating COI for dog {dog_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error calculating COI: {str(e)}")

    async def _build_pedigree_tree(self, dog: Dog, max_generations: int) -> Dict:
        pedigree = {}
        await self._add_ancestors_to_tree(dog, pedigree, max_generations, 0)
        return pedigree

    async def _add_ancestors_to_tree(self, dog: Dog, tree: Dict, max_generations: int, current_generation: int):
        if not dog or current_generation >= max_generations:
            return
        
        tree[dog.id] = {
            'id': dog.id,
            'name': dog.registered_name,
            'generation': current_generation,
            'sire_id': dog.sire_id,
            'dam_id': dog.dam_id,
            'coi': dog.coi or 0.0
        }
        
        # Add sire
        if dog.sire_id and dog.sire:
            await self.session.refresh(dog, ['sire'])
            await self._add_ancestors_to_tree(dog.sire, tree, max_generations, current_generation + 1)
        
        # Add dam
        if dog.dam_id and dog.dam:
            await self.session.refresh(dog, ['dam'])
            await self._add_ancestors_to_tree(dog.dam, tree, max_generations, current_generation + 1)

    def _calculate_coi_from_tree(self, pedigree_tree: Dict) -> Dict[str, Any]:
        if not pedigree_tree:
            return {
                'coi': 0.0,
                'generations_analyzed': 0,
                'common_ancestors': [],
                'details': []
            }
        main_dog_id = None
        for dog_id, dog_data in pedigree_tree.items():
            if dog_data['generation'] == 0:
                main_dog_id = dog_id
                break
        
        if not main_dog_id:
            return {
                'coi': 0.0,
                'generations_analyzed': 0,
                'common_ancestors': [],
                'details': []
            }
        
        main_dog = pedigree_tree[main_dog_id]
        sire_id = main_dog.get('sire_id')
        dam_id = main_dog.get('dam_id')
        
        if not sire_id or not dam_id:
            return {
                'coi': 0.0,
                'generations_analyzed': 0,
                'common_ancestors': [],
                'details': []
            }
        sire_ancestors = self._get_ancestors(pedigree_tree, sire_id)
        dam_ancestors = self._get_ancestors(pedigree_tree, dam_id)
        common_ancestors = sire_ancestors.intersection(dam_ancestors)
        
        coi = 0.0
        details = []
        generations_analyzed = max(
            max((pedigree_tree[dog_id]['generation'] for dog_id in pedigree_tree), default=0)
        )
        
        for ancestor_id in common_ancestors:
            ancestor = pedigree_tree[ancestor_id]
            sire_path = self._find_path_to_ancestor(pedigree_tree, sire_id, ancestor_id)
            dam_path = self._find_path_to_ancestor(pedigree_tree, dam_id, ancestor_id)
            
            if sire_path and dam_path:
                n1 = len(sire_path) - 1
                n2 = len(dam_path) - 1
                
                fa = ancestor.get('coi', 0.0)  # Inbreeding coefficient of the ancestor
                contribution = (0.5 ** (n1 + n2 + 1)) * (1 + fa)
                coi += contribution
                
                details.append({
                    'ancestor_id': ancestor_id,
                    'ancestor_name': ancestor['name'],
                    'generations_to_sire': n1,
                    'generations_to_dam': n2,
                    'ancestor_coi': fa,
                    'contribution': contribution,
                    'sire_path': sire_path,
                    'dam_path': dam_path
                })
        
        return {
            'coi': coi,
            'generations_analyzed': generations_analyzed,
            'common_ancestors': [
                {
                    'id': pedigree_tree[ancestor_id]['id'],
                    'name': pedigree_tree[ancestor_id]['name'],
                    'generation': pedigree_tree[ancestor_id]['generation']
                }
                for ancestor_id in common_ancestors
            ],
            'details': details
        }

    def _get_ancestors(self, pedigree_tree: Dict, dog_id: int) -> Set[int]:
        ancestors = set()
        
        def collect_ancestors(current_id: int):
            if current_id not in pedigree_tree:
                return
            
            dog_data = pedigree_tree[current_id]
            ancestors.add(current_id)
            
            if dog_data.get('sire_id'):
                collect_ancestors(dog_data['sire_id'])
            if dog_data.get('dam_id'):
                collect_ancestors(dog_data['dam_id'])
        
        collect_ancestors(dog_id)
        return ancestors

    def _find_path_to_ancestor(self, pedigree_tree: Dict, start_id: int, target_id: int) -> Optional[list]:
        if start_id not in pedigree_tree or target_id not in pedigree_tree:
            return None
        
        def find_path(current_id: int, path: list) -> Optional[list]:
            if current_id == target_id:
                return path + [current_id]
            
            if current_id not in pedigree_tree:
                return None
            
            dog_data = pedigree_tree[current_id]
            if dog_data.get('sire_id'):
                sire_path = find_path(dog_data['sire_id'], path + [current_id])
                if sire_path:
                    return sire_path
            if dog_data.get('dam_id'):
                dam_path = find_path(dog_data['dam_id'], path + [current_id])
                if dam_path:
                    return dam_path
            
            return None
        
        return find_path(start_id, [])

    async def get_dogs_paginated(
        self,
        page: int = 0,
        per_page: int = 15,
        date_of_birth_start: Optional[datetime] = None,
        date_of_birth_end: Optional[datetime] = None,
        date_of_death_start: Optional[datetime] = None,
        date_of_death_end: Optional[datetime] = None,
        modified_at_start: Optional[datetime] = None,
        modified_at_end: Optional[datetime] = None,
        **filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Build query with filters
        query = select(Dog).options(
            selectinload(Dog.titles),
            selectinload(Dog.owners),
            selectinload(Dog.breeders),
            selectinload(Dog.dam),
            selectinload(Dog.sire),
            selectinload(Dog.litters_as_dam),
            selectinload(Dog.litters_as_sire),
            selectinload(Dog.litters_as_mating_partner),
            selectinload(Dog.birth_litter),
            selectinload(Dog.siblings),
            selectinload(Dog.medical_records),
            selectinload(Dog.merge_logs),
        )
        
        conditions = []
        
        if filters.get("search"):
            search_term = f"%{filters['search']}%"
            conditions.append(or_(
                Dog.registered_name.ilike(search_term),
                Dog.registration_number.ilike(search_term),
                Dog.call_name.ilike(search_term),
                Dog.sire_name.ilike(search_term),
                Dog.dam_name.ilike(search_term)
            ))
                        
        if filters.get("color"):
            conditions.append(Dog.color.ilike(f"%{filters['color']}%"))
        if filters.get("land_of_birth"):
            conditions.append(Dog.land_of_birth == filters['land_of_birth'])
        if filters.get("land_of_standing"):
            conditions.append(Dog.land_of_standing == filters['land_of_standing'])

        # Булевы фильтры
        if filters.get("neutered") is not None:
            conditions.append(Dog.neutered == filters['neutered'])
        if filters.get("approved_for_breeding") is not None:
            conditions.append(Dog.approved_for_breeding == filters['approved_for_breeding'])
        if filters.get("frozen_semen") is not None:
            conditions.append(Dog.frozen_semen == filters['frozen_semen'])
        if filters.get("artificial_insemination") is not None:
            conditions.append(Dog.artificial_insemination == filters['artificial_insemination'])
        if filters.get("is_new") is not None:
            conditions.append(Dog.is_new == filters['is_new'])
        
        # Фильтр по наличию фото
        if filters.get("has_photo"):
            conditions.append(Dog.photo_url.is_not(None))
            
        # Фильтры по связанным сущностям
        if filters.get("owner_name"):
            subquery = select(DogOwnerLink.dog_id).join(Owner).where(
                Owner.name.ilike(f"%{filters['owner_name']}%")
            ).subquery()
            conditions.append(Dog.id.in_(subquery))
        
        if filters.get("breeder_name"):
            subquery = select(DogBreederLink.dog_id).join(Breeder).where(
                Breeder.name.ilike(f"%{filters['breeder_name']}%")
            ).subquery()
            conditions.append(Dog.id.in_(subquery))
            
        # Фильтры по дате рождения
        if date_of_birth_start or date_of_birth_end:
            date_conditions = []
            if date_of_birth_start:
                date_conditions.append(Dog.date_of_birth >= date_of_birth_start)
            if date_of_birth_end:
                date_conditions.append(Dog.date_of_birth <= date_of_birth_end)
            conditions.append(and_(*date_conditions))

        # Фильтры по дате смерти
        if date_of_death_start or date_of_death_end:
            date_conditions = []
            if date_of_death_start:
                date_conditions.append(Dog.date_of_death >= date_of_death_start)
            if date_of_death_end:
                date_conditions.append(Dog.date_of_death <= date_of_death_end)
            conditions.append(and_(*date_conditions))

        # Фильтры по дате модификации
        if modified_at_start or modified_at_end:
            date_conditions = []
            if modified_at_start:
                date_conditions.append(Dog.modified_at >= modified_at_start)
            if modified_at_end:
                date_conditions.append(Dog.modified_at <= modified_at_end)
            conditions.append(and_(*date_conditions))

        
        logger.info(f"Filters: {conditions}")
        
        if conditions:
            query = query.where(and_(*conditions))
            logger.info(f"Query with conditions: {query}")
        
        sort_column = filters.get('sort_by', 'id')
        sort_order = filters.get('sort_order', 'asc')
        
        column = getattr(Dog, sort_column, None)
        if column is not None:
            if sort_order.lower() == 'desc':
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        
        count_query = query.with_only_columns(func.count(Dog.id)).order_by(None)
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Get total count
        # total_result = await self.session.execute(
        #     query.with_only_columns(func.count()).order_by(None)
        # )
        # total = total_result.scalar_one()

        # Apply pagination
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.session.execute(query)
        dogs = result.scalars().all()

        total_pages = (total + per_page - 1) // per_page
        has_more = page < total_pages

        return {
            "data": dogs,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_more": has_more
            }
        }

    async def get_pedigree(self, dog_id: int, generations: int) -> Dict:
        async def get_ancestors(dog: Dog, depth: int) -> Optional[Dict]:
            if depth == 0 or not dog:
                return None

            await self.session.refresh(dog, ["dam", "sire"])
            
            return {
                "id": dog.id,
                "name": dog.registered_name,
                "dam": await get_ancestors(dog.dam, depth-1) if dog.dam else None,
                "sire": await get_ancestors(dog.sire, depth-1) if dog.sire else None
            }

        dog = await self.get_dog_by_id(dog_id)
        return await get_ancestors(dog, generations)

    async def update_notes(self, dog_id: int, notes: str = None, data_correctness_notes: str = None) -> Dog:
        result = await self.session.execute(
            select(Dog).where(Dog.id == dog_id)
        )
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        if notes is not None:
            dog.notes = notes
        if data_correctness_notes is not None:
            dog.data_correctness_notes = data_correctness_notes
        await self.session.commit()
        await self.session.refresh(dog)
        return dog

    async def export_dog_pedigree(self, dog_id: int) -> Tuple[str, str]:
        # Получаем собаку с родителями (до 5 поколений)
        result = await self.session.execute(
            select(Dog)
            .where(Dog.id == dog_id)
            .options(
                selectinload(Dog.sire).selectinload(Dog.sire),
                selectinload(Dog.sire).selectinload(Dog.dam),
                selectinload(Dog.dam).selectinload(Dog.sire),
                selectinload(Dog.dam).selectinload(Dog.dam),
                selectinload(Dog.sire),
                selectinload(Dog.dam),
            )
        )
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        
        # Собираем всех предков
        collected = collect_pedigree(dog, max_depth=5)
        
        # Строим граф
        dot = build_pedigree_graph(dog, collected)
        
        # Сохраняем во временный PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmpfile:
            dot.render(tmpfile.name, format='pdf', cleanup=True)
            pdf_path = tmpfile.name + '.pdf'
        
        filename = f"dog_{dog_id}_pedigree.pdf"
        return pdf_path, filename
