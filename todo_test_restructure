# Test Restructure Notes

These tests look like they were refactored down to low-signal checks (implementation details, dataclass wiring, or string properties). Consider removing, consolidating, or moving them as part of a test suite cleanup.

**Likely Low-Signal / Refactor Artifacts**
- tests/test_preprocessing.py: TestGrayscaleStep.test_name_property
- tests/test_preprocessing.py: TestResizeStep.test_name_property
- tests/test_preprocessing.py: TestCLAHEStep.test_default_parameters
- tests/test_preprocessing.py: TestCLAHEStep.test_is_frozen_dataclass
- tests/test_preprocessing.py: TestGrayscaleStep.test_is_frozen_dataclass
- tests/test_preprocessing.py: TestPreprocessConfig.test_config_is_immutable
- tests/test_preprocessing.py: TestPipeline.test_len_returns_step_count
- tests/test_preprocessing.py: TestPipeline.test_iter_yields_steps
- tests/test_bib_detection.py: TestDetectionDataclass.test_detection_default_source
- tests/test_bib_detection.py: TestDetectionDataclass.test_detection_from_dict
- tests/test_bib_detection.py: TestDetectionDataclass.test_detection_from_dict_with_source
- tests/test_bib_detection.py: TestBibCandidate.test_bib_candidate_creation
- tests/test_bib_detection.py: TestBibCandidate.test_bib_candidate_to_xywh
- tests/test_photo.py: TestPhotoToDict.test_includes_all_fields
- tests/test_photo.py: TestPhotoFromDbRow.test_handles_missing_optional_fields
- tests/test_photo.py: TestPhotoFromLocalPath.test_thumbnail_is_none

**Potential Consolidations (Reduce Duplication)**
- tests/test_preprocessing.py: multiple "pure function / no mutation" tests across steps can be represented by 1-2 representative tests.
- tests/test_preprocessing.py: multiple grayscale/resize shape tests can be parameterized to shrink suite without losing coverage.

**Misplaced (Should Move, Not Drop)**
- tests/test_bib_detection.py: TestDatabase (move to tests/test_db.py)
- tests/test_bib_detection.py: TestSnippetGeneration (move to tests/test_utils.py or tests/test_snippets.py)
- tests/test_bib_detection.py: TestBibDetection (mark slow/integration)
- tests/test_faces_artifacts.py: integration/slow (file IO + OpenCV)
