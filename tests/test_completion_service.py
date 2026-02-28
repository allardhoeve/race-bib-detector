"""Tests for benchmarking/services/completion_service.py."""
from __future__ import annotations

import pytest

from benchmarking.ground_truth import (
    BibBox,
    BibFaceLink,
    BibPhotoLabel,
    BibGroundTruth,
    FaceBox,
    FacePhotoLabel,
    FaceGroundTruth,
    LinkGroundTruth,
    save_bib_ground_truth,
    save_face_ground_truth,
    save_link_ground_truth,
)
from benchmarking.services.completion_service import (
    get_link_ready_hashes,
    get_unlinked_hashes,
    get_underlinked_hashes,
    get_bib_progress,
    get_face_progress,
    get_link_progress,
    workflow_context_for,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    bib_path = tmp_path / "bib_ground_truth.json"
    face_path = tmp_path / "face_ground_truth.json"
    link_path = tmp_path / "bib_face_links.json"
    index_path = tmp_path / "photo_index.json"
    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_path)
    monkeypatch.setattr("benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path)


def _save_index(tmp_path, hashes: list[str]) -> None:
    from benchmarking.photo_index import save_photo_index
    index_path = tmp_path / "photo_index.json"
    save_photo_index({h: [f"/photos/{h[:8]}.jpg"] for h in hashes}, index_path)


def _bib_label(h: str, labeled: bool = True) -> BibPhotoLabel:
    return BibPhotoLabel(content_hash=h, labeled=labeled)


def _face_label(h: str, labeled: bool = True) -> FacePhotoLabel:
    return FacePhotoLabel(content_hash=h, labeled=labeled)


class TestGetLinkReadyHashes:
    def test_requires_both_labeled(self, tmp_path):
        """Photo with only bib labeled is excluded."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=False))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == []

    def test_requires_face_labeled(self, tmp_path):
        """Photo with only face labeled is excluded."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=False))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == []

    def test_includes_when_both_done(self, tmp_path):
        """Photo with both bib and face labeled is included."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == [HASH_A]

    def test_mixed_set(self, tmp_path):
        """Only photos where both dimensions are labeled appear."""
        _save_index(tmp_path, [HASH_A, HASH_B, HASH_C])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_B, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_C, labeled=False))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        face_gt.add_photo(_face_label(HASH_B, labeled=False))
        face_gt.add_photo(_face_label(HASH_C, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == [HASH_A]


class TestGetUnlinkedHashes:
    def test_excludes_already_linked(self, tmp_path):
        """Photo already in link GT does not appear in unlinked list."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_unlinked_hashes() == []

    def test_includes_link_ready_without_links(self, tmp_path):
        """Link-ready photo with no link GT entry appears in unlinked list."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(LinkGroundTruth())

        assert get_unlinked_hashes() == [HASH_A]


class TestGetUnderlinkedHashes:
    def _setup_link_ready(self, tmp_path, hashes: list[str]) -> None:
        """Mark all hashes as bib+face labeled (link-ready)."""
        _save_index(tmp_path, hashes)
        bib_gt = BibGroundTruth()
        face_gt = FaceGroundTruth()
        for h in hashes:
            bib_gt.add_photo(_bib_label(h, labeled=True))
            face_gt.add_photo(_face_label(h, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

    def test_unprocessed_excluded(self, tmp_path):
        """Photo not yet in link GT is excluded (not processed)."""
        self._setup_link_ready(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=HASH_A, labeled=True,
            boxes=[BibBox(x=0, y=0, w=0.1, h=0.1, number='42', scope='bib')],
        ))
        save_bib_ground_truth(bib_gt)
        save_link_ground_truth(LinkGroundTruth())

        assert get_underlinked_hashes() == []

    def test_no_numbered_bibs_not_underlinked(self, tmp_path):
        """Photo with zero numbered bibs and zero links is not underlinked."""
        self._setup_link_ready(tmp_path, [HASH_A])
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])
        save_link_ground_truth(link_gt)

        assert get_underlinked_hashes() == []

    def test_links_match_numbered_bibs_not_underlinked(self, tmp_path):
        """Photo where link count equals numbered bib count is not underlinked."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=HASH_A, labeled=True,
            boxes=[BibBox(x=0, y=0, w=0.1, h=0.1, number='42', scope='bib')],
        ))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [BibFaceLink(bib_index=0, face_index=0)])
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_underlinked_hashes() == []

    def test_fewer_links_than_numbered_bibs(self, tmp_path):
        """Photo with fewer links than numbered bibs is underlinked."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=HASH_A, labeled=True,
            boxes=[
                BibBox(x=0, y=0, w=0.1, h=0.1, number='42', scope='bib'),
                BibBox(x=0.5, y=0, w=0.1, h=0.1, number='99', scope='bib'),
            ],
        ))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [BibFaceLink(bib_index=0, face_index=0)])  # only 1 of 2
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_underlinked_hashes() == [HASH_A]

    def test_unscored_scopes_excluded_from_count(self, tmp_path):
        """not_bib and bib_obscured boxes do not count toward numbered bib total."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=HASH_A, labeled=True,
            boxes=[
                BibBox(x=0, y=0, w=0.1, h=0.1, number='42', scope='not_bib'),
                BibBox(x=0.5, y=0, w=0.1, h=0.1, number='99', scope='bib_obscured'),
            ],
        ))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])  # zero links, but zero numbered bibs too
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_underlinked_hashes() == []

    def test_zero_links_with_numbered_bib(self, tmp_path):
        """Processed photo with numbered bibs but no links is underlinked."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=HASH_A, labeled=True,
            boxes=[BibBox(x=0, y=0, w=0.1, h=0.1, number='42', scope='bib')],
        ))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])  # processed but no links
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_underlinked_hashes() == [HASH_A]


class TestGetBibProgress:
    def test_counts_labeled(self, tmp_path):
        """Only photos with labeled=True are counted as done."""
        _save_index(tmp_path, [HASH_A, HASH_B])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_B, labeled=False))
        save_bib_ground_truth(bib_gt)

        assert get_bib_progress() == (1, 2)

    def test_zero_when_none_labeled(self, tmp_path):
        """Total reflects index size even when no labels exist."""
        _save_index(tmp_path, [HASH_A])
        save_bib_ground_truth(BibGroundTruth())

        assert get_bib_progress() == (0, 1)


class TestGetFaceProgress:
    def test_counts_labeled(self, tmp_path):
        """Returns correct (done, total) for face labeling."""
        _save_index(tmp_path, [HASH_A, HASH_B, HASH_C])
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        face_gt.add_photo(_face_label(HASH_B, labeled=True))
        face_gt.add_photo(_face_label(HASH_C, labeled=False))
        save_face_ground_truth(face_gt)

        assert get_face_progress() == (2, 3)


class TestGetLinkProgress:
    def test_denominator_is_link_ready_total(self, tmp_path):
        """Denominator is link-ready count, not all photos."""
        _save_index(tmp_path, [HASH_A, HASH_B, HASH_C])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_B, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_C, labeled=False))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        face_gt.add_photo(_face_label(HASH_B, labeled=True))
        face_gt.add_photo(_face_label(HASH_C, labeled=True))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        # A and B are link-ready; only A has links saved → (1, 2)
        assert get_link_progress() == (1, 2)


class TestWorkflowContextFor:
    def _setup_both_labeled(self, tmp_path):
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(LinkGroundTruth())

    def test_bib_step_flags(self, tmp_path):
        """active_step, bib_labeled, face_labeled, link_ready set correctly."""
        self._setup_both_labeled(tmp_path)
        ctx = workflow_context_for(HASH_A, 'bibs')

        assert ctx['active_step'] == 'bibs'
        assert ctx['bib_labeled'] is True
        assert ctx['face_labeled'] is True
        assert ctx['link_ready'] is True
        assert ctx['links_saved'] is False

    def test_bib_progress_shape(self, tmp_path):
        """Progress values are dicts with 'done' and 'total' keys."""
        self._setup_both_labeled(tmp_path)
        ctx = workflow_context_for(HASH_A, 'bibs')

        assert ctx['bib_progress'] == {'done': 1, 'total': 1}
        assert ctx['face_progress'] == {'done': 1, 'total': 1}
        assert ctx['link_progress'] == {'done': 0, 'total': 1}

    def test_links_disabled_when_not_ready(self, tmp_path):
        """link_ready=False when face labeling is incomplete."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=False))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(LinkGroundTruth())

        ctx = workflow_context_for(HASH_A, 'faces')

        assert ctx['link_ready'] is False
        assert ctx['links_saved'] is False
