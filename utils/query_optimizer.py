from sqlalchemy.orm import joinedload, selectinload, subqueryload
def optimize_query(model, relationships=None, strategy='joined'):
    if not relationships:
        return model.query
    
    query = model.query
    
    for rel in relationships:
        if strategy == 'joined':
            query = query.options(joinedload(getattr(model, rel)))
        elif strategy == 'select':
            query = query.options(selectinload(getattr(model, rel)))
        elif strategy == 'subquery':
            query = query.options(subqueryload(getattr(model, rel)))
    
    return query


def paginate_optimized(query, page=1, per_page=20):
    return query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100
    )


def batch_fetch(model, ids, relationships=None):
    query = model.query.filter(model.id.in_(ids))
    
    if relationships:
        for rel in relationships:
            query = query.options(joinedload(getattr(model, rel)))
    
    results = query.all()
    return {item.id: item for item in results}


def prefetch_related(instances, relationship_name, related_model):
    if not instances:
        return instances
    
    instance_ids = [instance.id for instance in instances]
    
    foreign_key = f'{instances[0].__tablename__}_id'
    related_items = related_model.query.filter(
        getattr(related_model, foreign_key).in_(instance_ids)
    ).all()
    
    related_map = {}
    for item in related_items:
        fk_value = getattr(item, foreign_key)
        if fk_value not in related_map:
            related_map[fk_value] = []
        related_map[fk_value].append(item)
    
    for instance in instances:
        setattr(instance, f'_prefetched_{relationship_name}', related_map.get(instance.id, []))
    
    return instances

