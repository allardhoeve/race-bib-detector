"""Tests for benchmarking.routes.ui.nav — resolve_photo_nav helper."""

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse
from starlette.testclient import TestClient

from benchmarking.photo_index import save_photo_index
from benchmarking.routes.ui.nav import PhotoNavContext, resolve_photo_nav

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_FROZEN = "f" * 64


def _build_app():
    """Build a minimal FastAPI app with a test route and a frozen_photo_detail route."""
    app = FastAPI()
    router = APIRouter()

    @router.get('/photos/{content_hash}')
    async def test_photo(content_hash: str, request: Request):
        # Used by tests — calls resolve_photo_nav with a fixed hash list
        hashes = request.state.filtered_hashes
        filter_suffix = request.state.filter_suffix
        result = resolve_photo_nav(
            content_hash, hashes, request, 'test_photo', filter_suffix,
        )
        if isinstance(result, RedirectResponse):
            return result
        return {
            'full_hash': result.full_hash,
            'idx': result.idx,
            'total': result.total,
            'prev_url': result.prev_url,
            'next_url': result.next_url,
            'all_index_keys': sorted(result.all_index.keys()),
        }

    @router.get('/frozen/{set_name}/{content_hash}')
    async def frozen_photo_detail(set_name: str, content_hash: str):
        return {'frozen': True, 'set_name': set_name}

    app.include_router(router)
    return app


@pytest.fixture
def nav_client(tmp_path, monkeypatch):
    """Test client with photo index containing HASH_A, HASH_B, HASH_C."""
    index_path = tmp_path / "photo_metadata.json"
    save_photo_index(
        {HASH_A: ["a.jpg"], HASH_B: ["b.jpg"], HASH_C: ["c.jpg"]},
        index_path,
    )
    monkeypatch.setattr(
        "benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path,
    )
    monkeypatch.setattr(
        "benchmarking.routes.ui.nav.is_frozen", lambda h: None,
    )

    app = _build_app()

    @app.middleware("http")
    async def inject_state(request: Request, call_next):
        request.state.filtered_hashes = sorted([HASH_A, HASH_B, HASH_C])
        request.state.filter_suffix = '?filter=all'
        return await call_next(request)

    return TestClient(app, follow_redirects=False)


class TestResolvePhotoNav:
    def test_returns_context_for_valid_hash(self, nav_client):
        resp = nav_client.get(f'/photos/{HASH_B[:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['full_hash'] == HASH_B
        assert data['total'] == 3

    def test_404_for_unknown_hash(self, nav_client):
        resp = nav_client.get('/photos/deadbeef')
        assert resp.status_code == 404

    def test_includes_all_index(self, nav_client):
        resp = nav_client.get(f'/photos/{HASH_A[:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert sorted(data['all_index_keys']) == sorted([HASH_A, HASH_B, HASH_C])

    def test_frozen_hash_redirects(self, tmp_path, monkeypatch):
        index_path = tmp_path / "photo_metadata.json"
        save_photo_index(
            {HASH_FROZEN: ["f.jpg"], HASH_A: ["a.jpg"]},
            index_path,
        )
        monkeypatch.setattr(
            "benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path,
        )
        monkeypatch.setattr(
            "benchmarking.routes.ui.nav.is_frozen",
            lambda h: "my_set" if h == HASH_FROZEN else None,
        )

        app = _build_app()

        @app.middleware("http")
        async def inject_state(request: Request, call_next):
            request.state.filtered_hashes = [HASH_A]
            request.state.filter_suffix = ''
            return await call_next(request)

        client = TestClient(app, follow_redirects=False)
        resp = client.get(f'/photos/{HASH_FROZEN[:8]}')
        assert resp.status_code == 302
        assert '/frozen/my_set/' in resp.headers['location']


class TestNavPrevNext:
    def test_first_item_has_no_prev(self, nav_client):
        hashes = sorted([HASH_A, HASH_B, HASH_C])
        resp = nav_client.get(f'/photos/{hashes[0][:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['prev_url'] is None
        assert data['next_url'] is not None
        assert data['idx'] == 0

    def test_last_item_has_no_next(self, nav_client):
        hashes = sorted([HASH_A, HASH_B, HASH_C])
        resp = nav_client.get(f'/photos/{hashes[-1][:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['prev_url'] is not None
        assert data['next_url'] is None
        assert data['idx'] == 2

    def test_middle_item_has_both(self, nav_client):
        hashes = sorted([HASH_A, HASH_B, HASH_C])
        resp = nav_client.get(f'/photos/{hashes[1][:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['prev_url'] is not None
        assert data['next_url'] is not None
        assert data['idx'] == 1

    def test_prev_next_urls_contain_filter_suffix(self, nav_client):
        hashes = sorted([HASH_A, HASH_B, HASH_C])
        resp = nav_client.get(f'/photos/{hashes[1][:8]}')
        data = resp.json()
        assert '?filter=all' in data['prev_url']
        assert '?filter=all' in data['next_url']

    def test_single_item_has_no_prev_or_next(self, tmp_path, monkeypatch):
        index_path = tmp_path / "photo_metadata.json"
        save_photo_index({HASH_A: ["a.jpg"]}, index_path)
        monkeypatch.setattr(
            "benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path,
        )
        monkeypatch.setattr(
            "benchmarking.routes.ui.nav.is_frozen", lambda h: None,
        )

        app = _build_app()

        @app.middleware("http")
        async def inject_state(request: Request, call_next):
            request.state.filtered_hashes = [HASH_A]
            request.state.filter_suffix = ''
            return await call_next(request)

        client = TestClient(app, follow_redirects=False)
        resp = client.get(f'/photos/{HASH_A[:8]}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['prev_url'] is None
        assert data['next_url'] is None
        assert data['total'] == 1


class TestNavFilteredVsFull:
    def test_hash_in_index_but_not_in_filter_returns_404(self, tmp_path, monkeypatch):
        """Hash exists in full index but not in filtered list → 404 (not frozen)."""
        index_path = tmp_path / "photo_metadata.json"
        save_photo_index(
            {HASH_A: ["a.jpg"], HASH_B: ["b.jpg"]},
            index_path,
        )
        monkeypatch.setattr(
            "benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path,
        )
        monkeypatch.setattr(
            "benchmarking.routes.ui.nav.is_frozen", lambda h: None,
        )

        app = _build_app()

        @app.middleware("http")
        async def inject_state(request: Request, call_next):
            # Only HASH_A is in the filtered list
            request.state.filtered_hashes = [HASH_A]
            request.state.filter_suffix = ''
            return await call_next(request)

        client = TestClient(app, follow_redirects=False)
        # HASH_B is in the index but not in filtered_hashes
        resp = client.get(f'/photos/{HASH_B[:8]}')
        assert resp.status_code == 404
