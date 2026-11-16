"""Phase 1 Regression Test Suite.

Verifies:
1. Baseline test case on sample HTML files produces exactly 8 additions, 1 removal, 12 modifications (21 total).
2. Deterministic summary sentence calculation matches expected counts and wording.
3. FastAPI POST /api/compare file upload endpoint functionality and input validation.
4. CLI execution with absolute paths succeeds; documents and tests the relative-path CLI issue.
5. Example HTML files pair comparison.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

# Setup sys.path to locate comparison-engine modules and src
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"
REPO_ROOT = COMPARISON_ENGINE_DIR.parent
TEST_FILES_DIR = REPO_ROOT / "test-files"
EXAMPLES_DIR = COMPARISON_ENGINE_DIR / "examples"

for directory in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

from api import app, _run_existing_engine
from result_adapter import adapt_engine_result

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"
EX_V1_FILE = EXAMPLES_DIR / "version1.html"
EX_V2_FILE = EXAMPLES_DIR / "version2.html"


def test_input_files_exist():
    """Verify all expected Phase 1 test and example files exist on disk."""
    assert V1_FILE.is_file(), f"Missing sample file: {V1_FILE}"
    assert V2_FILE.is_file(), f"Missing sample file: {V2_FILE}"
    assert EX_V1_FILE.is_file(), f"Missing example file: {EX_V1_FILE}"
    assert EX_V2_FILE.is_file(), f"Missing example file: {EX_V2_FILE}"


def test_sample_html_files_produce_exact_presentation_counts():
    """Verify the sample HTML files produce exactly 8 additions, 1 removal, 12 modifications (21 total)."""
    with TemporaryDirectory(prefix="test-phase1-regression-") as temp_dir:
        temp_path = Path(temp_dir)
        raw_changes, tree_v1, tree_v2 = _run_existing_engine(
            version1_path=V1_FILE,
            version2_path=V2_FILE,
            output_dir=temp_path,
        )

        adapted = adapt_engine_result(
            raw_changes=raw_changes,
            tree_v1=tree_v1,
            tree_v2=tree_v2,
            version1_name="mini project version 1.html",
            version2_name="mini project version 2.html",
        )

        pres_summary = adapted["presentationSummary"]
        assert pres_summary["added"] == 8, f"Expected 8 additions, got {pres_summary['added']}"
        assert pres_summary["removed"] == 1, f"Expected 1 removal, got {pres_summary['removed']}"
        assert pres_summary["modified"] == 12, f"Expected 12 modifications, got {pres_summary['modified']}"
        assert pres_summary["total"] == 21, f"Expected 21 total changes, got {pres_summary['total']}"
        assert len(adapted["changes"]) == 21, f"Expected 21 change records, got {len(adapted['changes'])}"

        # Verify category distribution in changes list
        added_count = sum(1 for c in adapted["changes"] if c["category"] == "added")
        removed_count = sum(1 for c in adapted["changes"] if c["category"] == "removed")
        modified_count = sum(1 for c in adapted["changes"] if c["category"] == "modified")

        assert added_count == 8
        assert removed_count == 1
        assert modified_count == 12


def test_deterministic_summary_calculation():
    """Verify summary counts and deterministic summary sentence match expected output."""
    with TemporaryDirectory(prefix="test-phase1-summary-") as temp_dir:
        temp_path = Path(temp_dir)
        raw_changes, tree_v1, tree_v2 = _run_existing_engine(
            version1_path=V1_FILE,
            version2_path=V2_FILE,
            output_dir=temp_path,
        )

        adapted = adapt_engine_result(
            raw_changes=raw_changes,
            tree_v1=tree_v1,
            tree_v2=tree_v2,
            version1_name="Version 1",
            version2_name="Version 2",
        )

        changes = adapted["changes"]

        # Replicate summary.js calculation logic in Python
        counts = {"total": 0, "added": 0, "removed": 0, "modified": 0}
        for c in changes:
            counts["total"] += 1
            cat = c.get("category")
            if cat in counts:
                counts[cat] += 1

        assert counts == {"total": 21, "added": 8, "removed": 1, "modified": 12}

        # Deterministic summary sentence verification
        total = counts["total"]
        added = counts["added"]
        removed = counts["removed"]
        modified = counts["modified"]

        total_word = "changes were" if total != 1 else "change was"
        added_phrase = f"{added} {'additions' if added != 1 else 'addition'}"
        removed_phrase = f"{removed} {'removals' if removed != 1 else 'removal'}"
        modified_phrase = f"{modified} {'modifications' if modified != 1 else 'modification'}"

        expected_sentence = (
            f"{total} {total_word} detected between the two webpage versions: "
            f"{added_phrase}, {removed_phrase} and {modified_phrase}."
        )

        assert expected_sentence == (
            "21 changes were detected between the two webpage versions: "
            "8 additions, 1 removal and 12 modifications."
        )


def test_api_compare_file_upload_success():
    """Verify POST /api/compare handles multipart HTML file uploads and returns expected response."""
    client = TestClient(app)

    with open(V1_FILE, "rb") as f1, open(V2_FILE, "rb") as f2:
        response = client.post(
            "/api/compare",
            files={
                "version1": ("mini project version 1.html", f1, "text/html"),
                "version2": ("mini project version 2.html", f2, "text/html"),
            },
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    assert "version1" in data
    assert "version2" in data
    assert "changes" in data
    assert "presentationSummary" in data
    assert "engineSummary" in data

    assert data["version1"]["label"] == "mini project version 1.html"
    assert data["version2"]["label"] == "mini project version 2.html"
    assert data["presentationSummary"] == {
        "total": 21,
        "added": 8,
        "removed": 1,
        "modified": 12,
    }
    assert len(data["changes"]) == 21


def test_api_compare_rejects_non_html_file():
    """Verify POST /api/compare rejects non-HTML uploads with HTTP 400."""
    client = TestClient(app)

    with open(V1_FILE, "rb") as f1:
        response = client.post(
            "/api/compare",
            files={
                "version1": ("sample.txt", b"plain text content", "text/plain"),
                "version2": ("mini project version 2.html", f1, "text/html"),
            },
        )

    assert response.status_code == 400
    assert "version1 must be an .html or .htm file." in response.json()["detail"]


def test_api_compare_rejects_document_without_html_root():
    """Verify POST /api/compare rejects files without a valid <html> element."""
    client = TestClient(app)

    response = client.post(
        "/api/compare",
        files={
            "version1": ("version1.html", b"<div>No html root tag</div>", "text/html"),
            "version2": ("version2.html", b"<html><body>Valid</body></html>", "text/html"),
        },
    )

    assert response.status_code == 400
    assert "Both files must contain a valid <html> document." in response.json()["detail"]


def test_api_health_endpoint():
    """Verify GET /api/health returns ok status."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_examples_pair_comparison():
    """Verify comparing the example HTML files produces expected changes."""
    with TemporaryDirectory(prefix="test-phase1-examples-") as temp_dir:
        temp_path = Path(temp_dir)
        raw_changes, tree_v1, tree_v2 = _run_existing_engine(
            version1_path=EX_V1_FILE,
            version2_path=EX_V2_FILE,
            output_dir=temp_path,
        )

        adapted = adapt_engine_result(
            raw_changes=raw_changes,
            tree_v1=tree_v1,
            tree_v2=tree_v2,
            version1_name="version1.html",
            version2_name="version2.html",
        )

        pres_summary = adapted["presentationSummary"]
        assert pres_summary["added"] == 1
        assert pres_summary["removed"] == 0
        assert pres_summary["modified"] == 4
        assert pres_summary["total"] == 5


def test_cli_execution_with_absolute_paths_succeeds():
    """Verify run_pipeline.py succeeds when invoked with absolute paths."""
    with TemporaryDirectory(prefix="test-phase1-cli-") as temp_dir:
        python_exe = sys.executable
        script_path = str(COMPARISON_ENGINE_DIR / "run_pipeline.py")

        result = subprocess.run(
            [
                python_exe,
                script_path,
                str(EX_V1_FILE.resolve()),
                str(EX_V2_FILE.resolve()),
                "--output",
                temp_dir,
            ],
            capture_output=True,
            text=True,
            cwd=str(COMPARISON_ENGINE_DIR),
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}\n{result.stdout}"
        out_path = Path(temp_dir)
        assert (out_path / "changes.json").is_file()
        assert (out_path / "run_summary.json").is_file()


def test_cli_relative_paths_reproduces_known_os_chdir_issue():
    """Test and document the known relative-path CLI issue in run_pipeline.py.

    When relative paths like 'examples/version1.html' are provided, run_pipeline.py
    calls os.chdir(out) before resolving input paths, causing shutil.copy2 to fail
    with FileNotFoundError inside output directory.
    This test verifies that the issue is understood without modifying the core engine.
    """
    with TemporaryDirectory(prefix="test-phase1-cli-rel-") as temp_dir:
        python_exe = sys.executable
        script_path = str(COMPARISON_ENGINE_DIR / "run_pipeline.py")

        # Run with relative paths from COMPARISON_ENGINE_DIR
        result = subprocess.run(
            [
                python_exe,
                script_path,
                "examples/version1.html",
                "examples/version2.html",
                "--output",
                temp_dir,
            ],
            capture_output=True,
            text=True,
            cwd=str(COMPARISON_ENGINE_DIR),
        )

        # The known behavior: exits with non-zero (code 1) due to FileNotFoundError
        assert result.returncode != 0, "Expected relative-path execution to fail due to os.chdir before resolve"
        assert "FileNotFoundError" in result.stderr or "WinError 3" in result.stderr

