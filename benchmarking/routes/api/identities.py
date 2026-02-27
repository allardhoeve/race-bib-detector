"""Identity management JSON API endpoints."""

from fastapi import APIRouter, HTTPException

from benchmarking.schemas import (
    CreateIdentityRequest,
    IdentitiesResponse,
    PatchIdentityRequest,
    PatchIdentityResponse,
)
from benchmarking.services.identity_service import (
    create_identity,
    list_identities,
    rename_identity_across_gt,
)

api_identities_router = APIRouter()


@api_identities_router.get('/api/identities', response_model=IdentitiesResponse)
async def get_identities() -> IdentitiesResponse:
    return IdentitiesResponse(identities=list_identities())


@api_identities_router.post('/api/identities', response_model=IdentitiesResponse)
async def post_identity(request: CreateIdentityRequest) -> IdentitiesResponse:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Missing name')
    ids = create_identity(name)
    return IdentitiesResponse(identities=ids)


@api_identities_router.patch('/api/identities/{name}', response_model=PatchIdentityResponse)
async def patch_identity(name: str, request: PatchIdentityRequest) -> PatchIdentityResponse:
    """Rename an identity across all face GT entries and the identities list."""
    new_name = request.new_name.strip()

    if not new_name:
        raise HTTPException(status_code=400, detail='Missing new_name')

    try:
        updated_count, ids = rename_identity_across_gt(name, new_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PatchIdentityResponse(updated_count=updated_count, identities=ids)
