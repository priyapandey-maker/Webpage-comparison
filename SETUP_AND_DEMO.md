# Historical Webpage Comparison — Setup, Installation & Demonstration Guide

This guide provides end-to-end instructions for installing, configuring, running, and demonstrating the **Historical Webpage Comparison** platform. It is formatted for evaluators, examiners, developers, and demonstrators.

---

## Table of Contents

1. [System Prerequisites](#1-system-prerequisites)
2. [Step-by-Step Installation](#2-step-by-step-installation)
   - [Backend Installation](#backend-installation)
   - [NLP Model Weights](#nlp-model-weights)
   - [Frontend Installation](#frontend-installation)
3. [Running the Application](#3-running-the-application)
   - [Starting the FastAPI Backend](#starting-the-fastapi-backend)
   - [Starting the React Frontend](#starting-the-react-frontend)
   - [Production Build Option](#production-build-option)
4. [Running Automated Tests](#4-running-automated-tests)
5. [Project Scope & Operational Boundaries](#5-project-scope--operational-boundaries)
   - [Implemented in the Current Project](#implemented-in-the-current-project)
   - [Outside Current Scope / Limitations](#outside-current-scope--limitations)
   - [Project Scope — Presentation Summary](#project-scope--presentation-summary)
   - [30-Second Summary for Faculty / HOD](#30-second-summary-for-faculty--hod)
6. [Supported Websites & Demonstration Catalogue](#6-supported-websites--demonstration-catalogue)
   - [Target Webpage Compatibility Criteria](#target-webpage-compatibility-criteria)
   - [Wayback Machine Requirements](#wayback-machine-requirements)
   - [Demonstration Test Catalogue](#demonstration-test-catalogue)
7. [Exact Scripted Demonstration Flows](#7-exact-scripted-demonstration-flows)
   - [Demo 1: Offline HTML File Comparison (`files`)](#demo-1-offline-html-file-comparison-files)
   - [Demo 2: Historical Wayback Snapshot Comparison & NLP (`wayback`)](#demo-2-historical-wayback-snapshot-comparison--nlp-wayback)
   - [Demo 3: SSRF & Security Defense Demonstration](#demo-3-ssrf--security-defense-demonstration)
8. [Troubleshooting & FAQ](#8-troubleshooting--faq)

---

## 1. System Prerequisites

Before setting up the project, ensure your workstation meets the following requirements:

| Component | Minimum Version | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10+ | 3.10, 3.11, or 3.12 | **Recommended**: Python 3.10–3.12. (Python 3.14 lacks pre-compiled wheels for dependencies such as `lxml`). |
| **Node.js** | 18.0+ | 20.x LTS | Required for Vite and React frontend. |
| **npm** | 9.0+ | 10.x | Bundled with Node.js. |
| **Operating System**| Windows 10/11, macOS 12+, Linux (Ubuntu 20.04+) | Any | Cross-platform compatible. |
| **RAM** | 4 GB | 8 GB+ | Required to load local PyTorch transformer embeddings. |
| **Internet Access** | Yes (first run only) | High-speed | Needed to install packages and download NLP models (~90 MB). |

---

## 2. Step-by-Step Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/priyapandey-maker/Webpage-comparison.git
cd Webpage-comparison
```

---

### Backend Installation

1. Navigate to the `comparison-engine/` directory:
   ```bash
   cd comparison-engine
   ```

2. Create a clean Python virtual environment:
   - **Windows**:
     ```powershell
     python -m venv .venv
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     ```

3. Activate the virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Windows (Command Prompt)**:
     ```cmd
     .\.venv\Scripts\activate.bat
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. Upgrade pip and install backend dependencies:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### NLP Model Weights

The system uses two local NLP models that require zero external API keys:

1. **Sentence Transformers (`all-MiniLM-L6-v2`)**:
   - Downloads automatically upon the first invocation of semantic comparison.
   - Cached locally in `~/.cache/huggingface/hub/` (~90 MB).
   - If you wish to pre-cache the model before a demo, run:
     ```python
     python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
     ```

2. **spaCy Small English Pipeline (`en_core_web_sm`)**:
   - Download the spaCy language model using the activated virtual environment:
     ```bash
     python -m spacy download en_core_web_sm
     ```

---

### Frontend Installation

1. Open a new terminal window and navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```

2. Install all Node dependencies:
   ```bash
   npm install
   ```

---

## 3. Running the Application

### Starting the FastAPI Backend

From the `comparison-engine/` directory with `.venv` activated:

```bash
uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

- **API Endpoint**: `http://127.0.0.1:8000`
- **Interactive Swagger Documentation**: `http://127.0.0.1:8000/docs`
- **Alternative ReDoc UI**: `http://127.0.0.1:8000/redoc`

> [!NOTE]
> All backend routes are served under the `/api/` prefix (`/api/compare`, `/api/wayback/snapshots`, `/api/wayback/compare`, `/api/health`). Keep this terminal open while using the application.

---

### Starting the React Frontend

From the `frontend/` directory:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

- **Frontend Application URL**: `http://127.0.0.1:5173`

Open your web browser (Chrome, Edge, Firefox, or Safari) and navigate to `http://127.0.0.1:5173`.

---

### Production Build Option

If you prefer to run an optimized production build of the frontend rather than the dev server:

```bash
cd frontend
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```
Then access the app at `http://127.0.0.1:4173`.

---

## 4. Running Automated Tests

To verify that the complete system is operating properly, execute the backend test suite:

1. Open a terminal in `comparison-engine/`.
2. Activate `.venv`.
3. Run `pytest`:
   ```bash
   pytest tests/ -v
   ```

### Expected Test Output
All **272 tests** will execute and pass:
```text
======================= 272 passed in 44.34s =======================
```

### Test Suite Structure
| Test File | Tests Passed | Coverage Area |
| :--- | :--- | :--- |
| `tests/test_html_tree.py` | 5 | DOM tree construction, tag pruning, text normalization. |
| `tests/test_structural_compare.py` | 5 | Weighted matching scores, modification thresholds. |
| `tests/test_security.py` / `test_url_validator.py` | 50 | URL validation, IP literal parsing, private IP blocks. |
| `tests/test_pinned_transport.py` | 82 | AnyIO DNS pinning, SSRF IP blocking, redirect limits, socket peer checks. |
| `tests/test_nlp.py` | 47 | Cosine similarity, sentence embeddings, NER regex fallback, keyword shifts. |
| `tests/test_live_compare.py` | 11 | HTML content-type validation, status checking, 404 retirement verification. |
| `tests/test_wayback.py` | 48 | Wayback CDX API queries, monthly collapsing, raw replay fetching. |
| `tests/test_api_wayback.py` | 24 | FastAPI `/api/wayback/*` route contracts, parameter validation, error mapping. |

---

## 5. Project Scope & Operational Boundaries

### Implemented in the Current Project
- **Two Comparison Modes**: HTML file upload (`files`) and historical Wayback comparison (`wayback`).
- **Same-Webpage Focus**: Strictly scoped to comparing different versions of the *same* original webpage (via local files or Wayback historical captures).
- **DOM / Structural Change Detection**: DOM tree building, tag pruning, and bipartite matching with weighted similarity scoring.
- **Categorized Change Reporting**: Explicit classification of additions, removals, and modifications across semantic elements (`Heading`, `Paragraph`, `Link`, `Button`, `Page title`).
- **Granular NLP Analysis of Modified Text**: Sentence Transformers (`all-MiniLM-L6-v2`) computing cosine similarity across matched modified text items, with deterministic token Jaccard fallback.
- **Entity and Keyword Dynamics**: spaCy NER identifying added, removed, and shared entities (`ORG`, `PERSON`, `GPE`, `DATE`, `MONEY`, `PERCENT`) with regex fallback, alongside noun chunk and keyword extraction.
- **SSRF-Aware Network Hardening**: Asynchronous DNS pinning using a custom `httpcore` AnyIO backend, private IP address blocking (RFC 1918, RFC 3927, loopback, cloud metadata), fail-closed socket peer verification, 10 MB payload limits, and 20s deadlines.
- **Interactive Web Interface**: Single-page React dashboard built with Vite and custom CSS (`styles.css`), backed by a Python FastAPI REST API.

---

### Outside Current Scope / Limitations
To ensure academic honesty, the following capabilities are explicitly outside the current implementation scope:
- **No Client-Side JavaScript Execution**: The engine does not execute JavaScript. Single-Page Applications (SPAs) that require client-side execution without Server-Side Rendering (SSR) expose only initial skeleton HTML.
- **No Headless Browser Automation**: The application uses direct HTTP streaming clients; it does not drive a browser instance (such as Puppeteer, Playwright, or Selenium) for snapshot retrieval.
- **Visual Screenshot Previews (Milestone 2)**: Full visual side-by-side screenshot rendering is scheduled for Milestone 2 (current release provides structural DOM diffs, attribute changes, and textual diffs).
- **Plain-English Explanations (Milestone 3)**: High-level natural language revision narratives are planned for Milestone 3 (current NLP provides semantic similarity scores, entity extraction, and keyword comparison).
- **No Two-URL Arbitrary Comparison**: The platform is strictly scoped to comparing versions of the *same* original webpage; comparing two arbitrary unrelated URLs is intentionally excluded.
- **No Recursive Domain Crawling**: The tool compares specific individual documents or URLs; it does not crawl an entire website domain recursively.
- **No Multi-Page Automated Crawling**: It operates on single-page pairs, not automated directory trees.
- **No Authentication or Cookie Sessions**: It does not support login-gated pages, paywalled content, or cookie-based sessions.
- **No Guaranteed Archive Availability**: Snapshot availability is subject to whether the Internet Archive has crawled and indexed the target page.
- **No Background Monitoring / Cron Alerting**: It performs on-demand comparisons; it does not continuously poll websites in the background for future changes.

---

### Project Scope — Presentation Summary
*(Suitable for project reports, viva slides, and formal presentations)*

> **System Overview**: Historical Webpage Comparison is a full-stack automated intelligence system that tracks structural, textual, and semantic revisions between different versions of the same webpage. The platform operates across two modes: offline HTML file comparison and historical Internet Archive snapshot comparison.
>
> **Core Architecture**: The engine parses raw HTML into Document Object Model trees, strips non-content tags, aligns corresponding elements using a 4-component weighted structural matcher, and calculates on-device semantic similarity using Sentence Transformers. The network layer is hardened against Server-Side Request Forgery (SSRF) and DNS rebinding attacks through asynchronous socket pinning.
>
> **Target Workload**: The application is designed for publicly accessible, server-rendered HTML pages, legal disclosures, policy documents, and archived captures. It evaluates on-demand comparisons for single-page pairs within a 10 MB streaming ceiling.
>
> **Key Distinctions**: The system compares different versions of the SAME original webpage—either supplied directly as HTML files or fetched as historical snapshots from the Wayback Machine. Semantic similarity is evaluated specifically across matched modified text items to detect meaning drift, rather than whole-page document classification.
>
> **Why It Is Useful**: It reduces superficial diff noise caused by whitespace, attribute ordering, and minor markup changes by matching DOM node hierarchies, helping reviewers focus on meaningful content additions, removals, and text updates.

---

### 30-Second Summary for Faculty / HOD
> "Our project is an automated webpage revision tracking platform that bridges the gap between syntactic line diffs and human semantic understanding. It takes two versions of a webpage—from local files or historical Wayback snapshots—builds a normalized DOM tree, and uses a weighted scoring algorithm to detect added, removed, and modified elements. For modified text, it runs an on-device Sentence Transformer to measure whether wording revisions actually changed the meaning, while our network layer mitigates SSRF and DNS rebinding risks through IP blacklisting, custom AnyIO socket pinning, and fail-closed peer-address verification. It focuses on server-rendered HTML without client-side JavaScript execution."

---

## 6. Supported Websites & Demonstration Catalogue

---

### Target Webpage Compatibility Criteria
Historical Webpage Comparison via Wayback Machine requires that target websites satisfy the following operational requirements:
1. **Protocol**: Must use standard `http://` or `https://`.
2. **Server-Rendered HTML**: Must return parseable HTML markup (`text/html` or `application/xhtml+xml`) containing a valid `<html>` document root.
3. **No Authentication or Sessions**: Must be publicly accessible; pages behind login gates, paywalls, or requiring session cookies are not supported.
4. **No Anti-Bot or CAPTCHA Gates**: Must not be protected by anti-bot systems that block automated HTTP clients.
5. **Resource Limits**: Response body must be under 10 Megabytes and must respond within the 20-second connection deadline.

---

### Wayback Machine Requirements
Wayback Machine comparison additionally requires:
1. **CDX Indexing**: The target website must have been crawled and indexed by the Internet Archive CDX API.
2. **Usable Capture Count**: There must be at least two usable captures with HTTP 200 status and HTML media type.
3. **Valid HTML Replay**: The archived HTML must be retrievable via `web.archive.org/web/{timestamp}id_/{url}` without redirecting to a different timestamp (`FallbackRedirectError`).
4. **Security Policy**: All replay requests must strictly reside on `web.archive.org` on HTTPS port 443.

---

### Demonstration Test Catalogue

| Website | Webpage URL | Suitability | Wayback Availability | Historical Captures Checked | Purpose in Demo | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **IANA Home** | `https://www.iana.org` | High; clean HTML, fast response (6.2 KB) | High; 24 monthly captures (2022–2023) | `20220128084535` vs `20231231222555` | Mode 2 Historical comparison & NLP | **Verified working** |
| **Python.org** | `https://www.python.org` | High; rich content, news (52 KB) | High; 24 monthly captures (2022–2023) | `20220131220219` vs `20231231231051` | Content-rich historical comparison | **Verified working** |
| **MIT Homepage** | `https://www.mit.edu` | High; articles and spotlight links (47.7 KB) | High; 24 monthly captures (2022–2023) | `20220131213846` vs `20231231132448` | Academic portal comparison | **Verified working** |
| **Wikipedia Portal** | `https://www.wikipedia.org` | High; multilingual portal (122 KB) | High; extensive historical archive | Not yet compared in engine | High-volume portal comparison | **Online accessible; Wayback needs verification** |
| **MDN Web Docs** | `https://developer.mozilla.org/en-US/` | Moderate; documentation home (116 KB) | Moderate; frequent Jamstack layout updates | Not yet compared in engine | Technical documentation diff | **Online accessible; Wayback needs verification** |
| **University of Michigan** | `https://umich.edu` | **Unsuitable**; returns HTTP 403 Forbidden to automated requests | CDX indexed | Blocked at transport | Demonstrating anti-bot / 403 handling | **Not suitable (HTTP 403)** |

---

## 7. Exact Scripted Demonstration Flows

Follow this step-by-step walkthrough during oral presentations or evaluations.

---

### Demo 1: Offline HTML File Comparison (`files`)

*Objective: Show high-speed, local DOM structural diffing without network dependency.*

1. **Navigate to the Application**: Open `http://127.0.0.1:5173` in your browser.
2. **Select Mode**: Click the **Upload HTML Files** tab (active by default).
3. **Choose Fixture Files**:
   - Under **Previous Version (Version 1)**, click the file input and select:
     `comparison-engine/examples/version1.html`
   - Under **Current Version (Version 2)**, click the file input and select:
     `comparison-engine/examples/version2.html`
4. **Execute**: Click **Compare Versions**.
5. **Evaluate Results**:
   - **Total Changes**: `5`
   - **Added**: `1` (New button labeled `"Start"`)
   - **Removed**: `0`
   - **Modified**: `4`
     1. *Link destination updated*: `/old` $\to$ `/new`
     2. *Heading text updated*: `"Welcome"` $\to$ `"Welcome to Version 2"`
     3. *Paragraph text updated*: `"Original text."` $\to$ `"Updated text."`
     4. *Page title text updated*: `"Demo Page"` $\to$ `"Updated Demo Page"`
6. **Interact with Filters**:
   - Click the **Added (1)** filter tab $\to$ only the button card appears.
   - Click the **Modified (4)** filter tab $\to$ the four text/link cards appear.
   - Click the **All (5)** filter tab $\to$ all cards reappear.
7. **Return**: Click **← Compare another pair** to return to the home screen.

> [!NOTE]
> Keep this separate from `test-files/mini project`, which contains a different test fixture pair producing 21 changes (8 additions, 1 removal, 12 modifications).

---

### Demo 2: Historical Wayback Snapshot Comparison & NLP (`wayback`)

*Objective: Demonstrate automatic historical snapshot discovery, temporal comparison between versions of the same webpage, and transformer-based semantic NLP analysis.*

1. **Select Mode**: Click the **Wayback Historical Comparison** tab.
2. **Input URL & Range**:
   - **Website URL**: `https://www.iana.org`
   - **From Year**: `2022`
   - **To Year**: `2023`
3. **Discover Snapshots**: Click **Find Snapshots**.
   - *Observe*: The client queries `web.archive.org/cdx/search/cdx` using monthly collapsing (`timestamp:6`).
   - Two dropdown selectors appear listing up to 50 curated monthly captures.
4. **Demonstrate Discovery Invalidation**:
   - Edit the **Website URL** field or change **To Year** to `2022`.
   - *Observe*: The snapshot dropdowns immediately disappear, selection state is cleared, and active requests are aborted via `AbortController`.
   - Restore the inputs and click **Find Snapshots** again.
5. **Select Verified Captures**:
   - **Snapshot 1 (Older)**: Select `20220128084535` (Jan 28, 2022 08:45 UTC).
   - **Snapshot 2 (Newer)**: Select `20231231222555` (Dec 31, 2023 22:25 UTC).
6. **Execute**: Click **Compare Historical Snapshots**.
   - *Observe*: The submit button displays a spinning loading indicator and changes label to "Comparing Historical Snapshots...".
7. **Evaluate Exact Results**:
   - **Verification Status**: **Freshly verified**
   - **Total Changes**: `6`
   - **Added**: `0`
   - **Removed**: `1` (Removed text element)
   - **Modified**: `5` (Updated headings and navigational links)
   - **Examine Section 02: Semantic Analysis of Modified Text**:
     - *Notice*: Displays reminder *"Applies strictly to matched text modifications; does not reflect whole-webpage similarity."*
     - **Average Semantic Similarity**: `44.0%` (Substantial Shift, score `0.4399`).
     - **Similarity Distribution Cards**: Shows breakdown across `Identical (≥99.9%)`, `High Overlap (80–99%)`, `Moderate Shift (50–79%)`, `Substantial Shift (25–49%)`, and `Different (<25%)`.
     - **Key Content Terms**: Displays key added terms (prefixed with `+`) and key removed terms (prefixed with `-`).
     - **Modified Text Item Details (Accordion)**: Expand any item to inspect side-by-side Before $\to$ After text, extracted keywords, and named entities.
   - **Examine Section 03: Detected Changes**:
     - Inspect modified titles, headings, and paragraph differences.

---

### Demo 3: SSRF & Security Defense Demonstration

*Objective: Prove that the application proactively defends against cyber attacks, private network snooping, and internal scanning.*

1. **Select Mode**: Click the **Wayback Historical Comparison** tab.
2. **Test 1 — Direct Loopback IP Address**:
   - Enter `http://127.0.0.1:8000` into **Website URL**.
   - Click **Find Snapshots**.
   - *Result*: Immediate rejection with error: `"Access to 127.0.0.1 is forbidden: Loopback address (127.0.0.1)."`.
3. **Test 2 — Localhost Domain Name**:
   - Enter `http://localhost:8000` into **Website URL**.
   - Click **Find Snapshots**.
   - *Result*: Rejection with error: `"Access to prohibited hostname 'localhost' is blocked."`.
4. **Test 3 — AWS / Cloud Metadata IP**:
   - Enter `http://169.254.169.254/latest/meta-data/` into **Website URL**.
   - Click **Find Snapshots**.
   - *Result*: Rejection with error: Link-local address forbidden (`169.254.0.0/16`).
5. **Test 4 — Public IP Literal (Permitted)**:
   - Enter `http://93.184.216.34` (example.com public IP) into **Website URL**.
   - Click **Find Snapshots**.
   - *Result*: The public IP literal is validated and accepted by the URL validator, safely proceeding to query CDX records.

---

## 8. Troubleshooting & FAQ

### 1. Port Already in Use (Address already in use: 8000 or 5173)
- **Problem**: Another process is occupying port 8000 (backend) or 5173 (frontend).
- **Solution**:
  - *Windows*:
    ```powershell
    Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
    ```
  - *Linux/macOS*:
    ```bash
    kill -9 $(lsof -t -i:8000)
    ```

### 2. PyTorch or Sentence Transformer First-Run Delay
- **Problem**: When running Historical Wayback comparison for the very first time, the request takes 5–10 seconds.
- **Explanation**: The library downloads `all-MiniLM-L6-v2` (~90 MB) into your local cache directory (`~/.cache/huggingface/hub/`). Subsequent runs load the model instantly from disk and execute inference in ~40 milliseconds, aided by the in-memory cache `_EMBEDDING_CACHE`.

### 3. Missing spaCy Model (`OSError: [E050] Can't find model 'en_core_web_sm'`)
- **Problem**: spaCy model was not downloaded into the active virtual environment.
- **Solution**:
  ```bash
  python -m spacy download en_core_web_sm
  ```

### 4. Internet Archive CDX Timeout or Rate Limit
- **Problem**: Querying Wayback Machine snapshots takes a long time or returns HTTP 504.
- **Explanation**: The Internet Archive public CDX API occasionally experiences rate limits or server latency. Narrow your year range (e.g., compare across 2 years instead of 10) or wait 30 seconds and retry.

### 5. Client-Side CORS Error
- **Problem**: Browser console reports `Access-Control-Allow-Origin` failure.
- **Explanation**: The API is configured with `allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$"`. Ensure you access the frontend via `http://localhost:5173` or `http://127.0.0.1:5173`.

---

*This guide is part of the official project documentation suite for Historical Webpage Comparison.*
