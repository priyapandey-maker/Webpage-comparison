"""Minimal local API wrapper around Member 2's existing comparison functions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from change_detector import detect_changes
from html_tree import build_tree, save_tree
from structural_compare import create_structural_matches
from structural_match import structural_match
from result_adapter import adapt_engine_result


app = FastAPI(title="Historical Webpage Comparison API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

# Member 2's functions use fixed filenames in the current working directory.
# The lock prevents two local requests from changing that directory at once.
ENGINE_LOCK = Lock()
HTML_EXTENSIONS = {".html", ".htm"}


def _run_existing_engine(version1_path: Path, version2_path: Path, output_dir: Path):
    """Orchestrate the existing functions exactly; no comparison logic lives here."""
    previous_directory = Path.cwd()
    with ENGINE_LOCK:
        os.chdir(output_dir)
        try:
            local_v1 = output_dir / "version1.html"
            local_v2 = output_dir / "version2.html"
            local_v1.write_bytes(version1_path.read_bytes())
            local_v2.write_bytes(version2_path.read_bytes())

            tree_v1 = build_tree(str(local_v1))
            tree_v2 = build_tree(str(local_v2))
            if tree_v1 is None or tree_v2 is None:
                raise ValueError("Both files must contain a valid <html> document.")

            save_tree(tree_v1, "tree_v1.json")
            save_tree(tree_v2, "tree_v2.json")
            structural_match(tree_v1, tree_v2)
            create_structural_matches()
            detect_changes()

            changes_path = output_dir / "changes.json"
            if not changes_path.exists():
                raise RuntimeError("The comparison engine did not produce changes.json.")
            raw_changes = json.loads(changes_path.read_text(encoding="utf-8"))
            return raw_changes, tree_v1, tree_v2
        finally:
            os.chdir(previous_directory)


def _validate_upload(upload: UploadFile, field_name: str) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in HTML_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an .html or .htm file.")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/compare")
async def compare(
    version1: UploadFile = File(...),
    version2: UploadFile = File(...),
):
    _validate_upload(version1, "version1")
    _validate_upload(version2, "version2")

    try:
        with TemporaryDirectory(prefix="webpage-comparison-") as temp_directory:
            temp_path = Path(temp_directory)
            version1_path = temp_path / "uploaded-version1.html"
            version2_path = temp_path / "uploaded-version2.html"
            version1_path.write_bytes(await version1.read())
            version2_path.write_bytes(await version2.read())

            raw_changes, tree_v1, tree_v2 = _run_existing_engine(
                version1_path,
                version2_path,
                temp_path,
            )
            return adapt_engine_result(
                raw_changes,
                tree_v1,
                tree_v2,
                version1.filename or "Version 1",
                version2.filename or "Version 2",
            )
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {error}") from error
    finally:
        await version1.close()
        await version2.close()
