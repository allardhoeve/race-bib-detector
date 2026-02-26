"""Identity management routes."""

from fastapi import APIRouter, Body, HTTPException

from benchmarking.services.identity_service import (
    list_identities,
    create_identity,
    rename_identity_across_gt,
)

identities_router = APIRouter()


@identities_router.get('/api/identities')
async def get_identities():
    return {'identities': list_identities()}


@identities_router.post('/api/identities')
async def post_identity(body: dict = Body(default={})):
    name = (body.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Missing name')
    ids = create_identity(name)
    return {'identities': ids}


@identities_router.post('/api/rename_identity', include_in_schema=False)
async def rename_identity_legacy():
    """Legacy rename endpoint — gone. Use PATCH /api/identities/<name>."""
    raise HTTPException(status_code=410, detail='Use PATCH /api/identities/<name>')


@identities_router.patch('/api/identities/{name}')
async def patch_identity(name: str, body: dict = Body(default={})):
    """Rename an identity across all face GT entries and the identities list."""
    new_name = (body.get('new_name') or '').strip()

    if not new_name:
        raise HTTPException(status_code=400, detail='Missing new_name')

    try:
        updated_count, ids = rename_identity_across_gt(name, new_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'updated_count': updated_count, 'identities': ids}
