"""Identity management JSON API endpoints."""

from fastapi import APIRouter, Body, HTTPException

from benchmarking.services.identity_service import (
    create_identity,
    list_identities,
    rename_identity_across_gt,
)

api_identities_router = APIRouter()


@api_identities_router.get('/api/identities')
async def get_identities():
    return {'identities': list_identities()}


@api_identities_router.post('/api/identities')
async def post_identity(body: dict = Body(default={})):
    name = (body.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Missing name')
    ids = create_identity(name)
    return {'identities': ids}


@api_identities_router.patch('/api/identities/{name}')
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
