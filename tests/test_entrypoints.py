import importlib

import pytest


ENTRYPOINTS = [
    "bnr",
    "download_by_bib",
    "list_detections",
    "web_viewer",
    "web.app",
    "benchmarking.cli",
    "benchmarking.web_app",
    "sources.google_photos",
]


@pytest.mark.parametrize("module_name", ENTRYPOINTS)
def test_entrypoint_help(module_name):
    module = importlib.import_module(module_name)
    assert hasattr(module, "main"), f"{module_name} missing main()"

    with pytest.raises(SystemExit) as excinfo:
        module.main(["--help"])

    assert excinfo.value.code == 0
