"""Minimal local API wrapper around Member 2's existing comparison functions."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import anyio
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from change_detector import detect_changes
from html_tree import build_tree, save_tree
from structural_compare import create_structural_matches
from structural_match import structural_match
from result_adapter import adapt_engine_result

from html_validator import HTMLValidationError
from nlp.pipeline import attach_nlp_analysis
from ai import generate_ai_summary
from security.ssrf_validator import (
    BlockedIPError,
    DNSResolutionError,
    InvalidURLError,
    PeerVerificationError,
    RedirectSecurityError,
    ResourceLimitError,
    SSRFSecurityError,
    TLSVerificationError,
)
from wayback_client import (
    FallbackRedirectError,
    InvalidWaybackURLError,
    OffHostRedirectError,
    SnapshotNotFoundError,
    WaybackCDXError,
    WaybackCompareRequest,
    WaybackContentError,
    WaybackError,
    WaybackFetchError,
    WaybackSnapshotsRequest,
    WaybackSnapshotsResponse,
    WaybackVerificationError,
    discover_wayback_snapshots,
    fetch_wayback_raw_pair,
    verify_and_resolve_snapshots,
)

logger = logging.getLogger(__name__)


app = FastAPI(title="Historical Webpage Comparison API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Member 2's functions use fixed filenames in the current working directory.
# The lock prevents two local requests from changing that directory at once.
ENGINE_LOCK = Lock()
HTML_EXTENSIONS = {".html", ".htm"}


class WaybackComparePayload(BaseModel):
    """Input payload schema for the Wayback snapshot comparison endpoint."""

    url: str
    timestamp1: str
    timestamp2: str


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
            adapted = adapt_engine_result(
                raw_changes,
                tree_v1,
                tree_v2,
                version1.filename or "Version 1",
                version2.filename or "Version 2",
            )
            try:
                enriched = attach_nlp_analysis(adapted)
            except Exception as err:
                logger.warning("NLP enrichment failed safely on file compare: %s", err)
                enriched = adapted

            # Enrich with local LLM AI explanation layer
            try:
                enriched["aiSummary"] = await generate_ai_summary(enriched)
            except Exception as err:
                logger.warning("AI summary generation failed safely on file compare: %s", err)
                enriched["aiSummary"] = None

            return enriched
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {error}") from error
    finally:
        await version1.close()
        await version2.close()


@app.get("/api/wayback/snapshots", response_model=WaybackSnapshotsResponse)
async def get_wayback_snapshots(
    url: str = Query(..., description="Target webpage URL to discover historical snapshots for"),
    from_year: int | None = Query(None, description="Optional start year filter (1996-2099)"),
    to_year: int | None = Query(None, description="Optional end year filter (1996-2099)"),
):
    """Discover available historical snapshots for a webpage URL from the Wayback Machine."""
    # 1. Pre-validation of query parameters
    try:
        req = WaybackSnapshotsRequest(
            url=url,
            from_year=from_year,
            to_year=to_year,
        )
    except ValidationError as err:
        errors = err.errors()
        msg = errors[0].get("msg", str(err)) if errors else str(err)
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        raise HTTPException(status_code=400, detail=f"Invalid snapshot request: {msg}")
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid snapshot request: {err}")

    # 2. Discover snapshots via CDX API
    try:
        return await discover_wayback_snapshots(req)
    except ResourceLimitError as err:
        logger.warning("Snapshot discovery resource limit exceeded: %s", err)
        err_str = str(err).lower()
        if "deadline" in err_str or "timeout" in err_str:
            raise HTTPException(
                status_code=504,
                detail="Gateway timeout: Request deadline exceeded while querying the Wayback Machine.",
            ) from err
        raise HTTPException(
            status_code=413,
            detail="Payload too large: Wayback snapshot index response exceeded maximum allowable size.",
        ) from err
    except (InvalidWaybackURLError, InvalidURLError, BlockedIPError, RedirectSecurityError, SSRFSecurityError) as err:
        raise HTTPException(status_code=400, detail=f"Security violation: {err}")
    except OffHostRedirectError as err:
        logger.warning("Snapshot discovery off-host redirect violation: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Wayback security violation: Request or redirect to unauthorized host is prohibited.",
        ) from err
    except (DNSResolutionError, TLSVerificationError, PeerVerificationError) as err:
        logger.warning("Snapshot discovery upstream connection failed: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Upstream connection failed: Unable to connect securely to Wayback services.",
        ) from err
    except WaybackCDXError as err:
        logger.warning("CDX discovery service error: %s", err)
        detail = (
            f"Upstream CDX service error: Wayback index query returned HTTP {err.status_code}."
            if err.status_code is not None
            else "Upstream CDX service error: The Wayback snapshot index returned an invalid response."
        )
        raise HTTPException(status_code=502, detail=detail) from err
    except (WaybackFetchError, WaybackError) as err:
        logger.warning("Wayback fetch error: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Upstream Wayback service failed: Unable to complete request to Wayback services.",
        ) from err
    except Exception as err:
        logger.error("Snapshot discovery failed: %s", err, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Snapshot discovery failed due to an unexpected internal error.",
        ) from err


@app.post("/api/wayback/compare")
async def compare_wayback_snapshots(payload: WaybackComparePayload):
    """Compare two historical Wayback captures of a webpage using the structural engine and NLP pipeline."""
    # 1. Validate payload using WaybackCompareRequest
    try:
        req = WaybackCompareRequest(
            url=payload.url,
            timestamp1=payload.timestamp1,
            timestamp2=payload.timestamp2,
        )
    except ValidationError as err:
        errors = err.errors()
        msg = errors[0].get("msg", str(err)) if errors else str(err)
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        raise HTTPException(status_code=400, detail=f"Invalid comparison request: {msg}")
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid comparison request: {err}")

    # 2. Verify snapshot records and fetch raw HTML captures concurrently
    try:
        snap1, snap2 = await verify_and_resolve_snapshots(
            req.url,
            req.timestamp1,
            req.timestamp2,
        )
        res1, res2 = await fetch_wayback_raw_pair(snap1, snap2, total_deadline=30.0)
    except SnapshotNotFoundError as err:
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {err}")
    except FallbackRedirectError as err:
        raise HTTPException(status_code=409, detail=f"Exact capture unavailable: {err}")
    except OffHostRedirectError as err:
        logger.warning("Wayback compare off-host redirect violation: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Wayback security violation: Request or redirect to unauthorized host is prohibited.",
        ) from err
    except ResourceLimitError as err:
        logger.warning("Wayback compare resource limit exceeded: %s", err)
        err_str = str(err).lower()
        if "deadline" in err_str or "timeout" in err_str:
            raise HTTPException(
                status_code=504,
                detail="Gateway timeout: Request deadline exceeded while retrieving archived capture.",
            ) from err
        raise HTTPException(
            status_code=413,
            detail="Payload too large: Archived capture exceeded maximum allowable size.",
        ) from err
    except (InvalidWaybackURLError, InvalidURLError, BlockedIPError, RedirectSecurityError, SSRFSecurityError) as err:
        raise HTTPException(status_code=400, detail=f"Security violation: {err}")
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid comparison request: {err}")
    except WaybackVerificationError as err:
        raise HTTPException(status_code=422, detail=f"Snapshot verification failed: {err}")
    except (WaybackContentError, HTMLValidationError) as err:
        raise HTTPException(status_code=422, detail=f"Archived HTML validation failed: {err}")
    except (DNSResolutionError, TLSVerificationError, PeerVerificationError) as err:
        logger.warning("Wayback comparison upstream connection failed: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Upstream connection failed: Unable to connect securely to Wayback services.",
        ) from err
    except (WaybackCDXError, WaybackFetchError, WaybackError) as err:
        logger.warning("Wayback compare upstream failure: %s", err)
        raise HTTPException(
            status_code=502,
            detail="Upstream Wayback service failed: Unable to retrieve archived capture from the Wayback Machine.",
        ) from err

    # 3. Write fetched bytes to isolated temporary directory and execute comparison engine
    try:
        with TemporaryDirectory(prefix="webpage-compare-wayback-") as temp_directory:
            temp_path = Path(temp_directory)
            version1_path = temp_path / "wayback-version1.html"
            version2_path = temp_path / "wayback-version2.html"

            # Preserve exact response bytes
            version1_path.write_bytes(res1.content)
            version2_path.write_bytes(res2.content)

            # Offload synchronous engine execution to worker thread to keep async event loop responsive
            raw_changes, tree_v1, tree_v2 = await anyio.to_thread.run_sync(
                _run_existing_engine,
                version1_path,
                version2_path,
                temp_path,
            )

            # Adapt engine output to frontend presentation schema using verified timestamps and URLs
            label1 = f"{snap1.original_url} ({snap1.timestamp} - {snap1.display_date})"
            label2 = f"{snap2.original_url} ({snap2.timestamp} - {snap2.display_date})"
            adapted = adapt_engine_result(
                raw_changes,
                tree_v1,
                tree_v2,
                label1,
                label2,
            )

            # Enrich with verified historical snapshot metadata & replay URLs for visual inspection
            replay1 = f"https://web.archive.org/web/{snap1.timestamp}/{snap1.original_url}"
            raw_replay1 = f"https://web.archive.org/web/{snap1.timestamp}id_/{snap1.original_url}"
            replay2 = f"https://web.archive.org/web/{snap2.timestamp}/{snap2.original_url}"
            raw_replay2 = f"https://web.archive.org/web/{snap2.timestamp}id_/{snap2.original_url}"

            wayback_ctx = {
                "targetUrl": req.url,
                "version1": {
                    "label": label1,
                    "timestamp": snap1.timestamp,
                    "datetime": snap1.datetime,
                    "displayDate": snap1.display_date,
                    "originalUrl": snap1.original_url,
                    "replayUrl": replay1,
                    "rawReplayUrl": raw_replay1,
                },
                "version2": {
                    "label": label2,
                    "timestamp": snap2.timestamp,
                    "datetime": snap2.datetime,
                    "displayDate": snap2.display_date,
                    "originalUrl": snap2.original_url,
                    "replayUrl": replay2,
                    "rawReplayUrl": raw_replay2,
                },
            }
            adapted["waybackContext"] = wayback_ctx
            adapted["version1"].update(wayback_ctx["version1"])
            adapted["version2"].update(wayback_ctx["version2"])

            # Enrich with NLP semantic analysis layer
            try:
                enriched = attach_nlp_analysis(adapted)
            except Exception as err:
                logger.warning("NLP enrichment failed safely on wayback compare: %s", err)
                enriched = adapted

            # Enrich with local LLM AI explanation layer
            try:
                enriched["aiSummary"] = await generate_ai_summary(enriched)
            except Exception as err:
                logger.warning("AI summary generation failed safely on wayback compare: %s", err)
                enriched["aiSummary"] = None

            return enriched
    except HTTPException:
        raise
    except ValueError as err:
        raise HTTPException(status_code=422, detail=f"HTML parsing failed: {err}")
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        logger.error("Document decode error: %s", err, exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Document decode error: Unable to parse document encoding or JSON structure.",
        ) from err
    except Exception as err:
        logger.error("Wayback comparison failed: %s", err, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Comparison failed due to an unexpected internal error.",
        ) from err
