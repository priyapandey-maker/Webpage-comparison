# Historical Webpage Comparison — Technical Architecture & Implementation Specification

This document provides the authoritative, in-depth technical specification of the **Historical Webpage Comparison** system. It details the mathematical formulas, algorithms, network hardening architecture, Natural Language Processing pipelines, data contracts, and implementation constraints of the platform.

---

## Table of Contents

1. [Problem Statement & Architectural Goals](#1-problem-statement--architectural-goals)
2. [Technology Stack & Dependency Matrix](#2-technology-stack--dependency-matrix)
3. [System Architecture & Module Hierarchy](#3-system-architecture--module-hierarchy)
4. [DOM Parsing & Tree Extraction (`html_tree.py`)](#4-dom-parsing--tree-extraction-html_treepy)
5. [Structural Comparison Algorithms & Mathematics](#5-structural-comparison-algorithms--mathematics)
   - [Weighted Node Similarity Formula (`structural_match.py`)](#weighted-node-similarity-formula-structural_matchpy)
   - [Change Detection & Node Similarity (`change_detector.py`)](#change-detection--node-similarity-change_detectorpy)
   - [Frontend Presentation Adaptation (`result_adapter.py`)](#frontend-presentation-adaptation-result_adapterpy)
6. [Natural Language Processing & Semantic Intelligence](#6-natural-language-processing--semantic-intelligence)
   - [Scope & Aggregation Architecture](#scope--aggregation-architecture)
   - [Sentence Transformer Embeddings & Cosine Mathematics](#sentence-transformer-embeddings--cosine-mathematics)
   - [Deterministic Fallback Similarity](#deterministic-fallback-similarity)
   - [Named Entity Recognition & Regex Fallback (`ner.py`)](#named-entity-recognition--regex-fallback-nerpy)
   - [Keyword & Noun Chunk Extraction (`keyword_extraction.py`)](#keyword--noun-chunk-extraction-keyword_extractionpy)
7. [Cybersecurity & Network Hardening Layer](#7-cybersecurity--network-hardening-layer)
   - [URL Validation & Invariant Enforcement (`ssrf_validator.py`)](#url-validation--invariant-enforcement-ssrf_validatorpy)
   - [Asynchronous DNS Pinning via AnyIO Backend (`pinned_transport.py`)](#asynchronous-dns-pinning-via-anyio-backend-pinned_transportpy)
   - [Fail-Closed Socket Verification](#fail-closed-socket-verification)
   - [Safe Manual Redirect Loop & RFC 9110 Rewriting (`redirect_handler.py`)](#safe-manual-redirect-loop--rfc-9110-rewriting-redirect_handlerpy)
   - [HTML Content Invariants & Sniffing Fallback (`live_compare.py`)](#html-content-invariants--sniffing-fallback-live_comparepy)
8. [Wayback Machine Historical Integration (`wayback_client.py`)](#8-wayback-machine-historical-integration-wayback_clientpy)
   - [Monthly CDX Snapshot Discovery & Truncation Detection](#monthly-cdx-snapshot-discovery--truncation-detection)
   - [Point Snapshot Verification](#point-snapshot-verification)
   - [Raw Replay Retrieval & Fallback Redirect Rejection](#raw-replay-retrieval--fallback-redirect-rejection)
   - [Error Hierarchy & HTTP Status Code Mapping](#error-hierarchy--http-status-code-mapping)
9. [API Specification & Data Schemas (`api.py`)](#9-api-specification--data-schemas-apipy)
10. [Frontend Architecture & State Machine](#10-frontend-architecture--state-machine)
11. [Verification Evidence & Automated Test Matrix](#11-verification-evidence--automated-test-matrix)
12. [Project Scope & Operational Boundaries](#12-project-scope--operational-boundaries)
   - [Implemented in the Current Project](#implemented-in-the-current-project)
   - [Outside Current Scope / Operational Limitations](#outside-current-scope--operational-limitations)
   - [Project Scope — Presentation Summary](#project-scope--presentation-summary)
   - [30-Second Summary for Faculty / HOD](#30-second-summary-for-faculty--hod)

---

## 1. Problem Statement & Architectural Goals

Tracking webpage modifications using raw text diffing (such as `git diff` or character Levenshtein distance) is inadequate for HTML documents. In web markup, trivial syntactic variations—such as reordered attributes, modified whitespace, or wrapping text inside a decorative `<span>`—generate hundreds of false-positive diff chunks while browser rendering remains identical. Conversely, critical content mutations (e.g., altered terms of service or pricing shifts) can be obscured inside large wrapper blocks.

Furthermore, allowing users to supply arbitrary URLs introduces severe cybersecurity vectors, most notably **Server-Side Request Forgery (SSRF)** and **DNS Rebinding** (Time-of-Check to Time-of-Use attacks).

### Core Architectural Goals:
1. **DOM-Level Structural Fidelity**: Parse HTML into clean DOM node hierarchies, strip ephemeral script/style noise, and align elements using a multi-factor weighted matching algorithm.
2. **Local AI & Semantic Intelligence**: Quantify semantic drift on detected text modifications using on-device sentence transformers and extract entity shifts using spaCy without external cloud dependencies.
3. **Hardened Network Boundary**: Prevent SSRF, DNS rebinding, and denial-of-service via asynchronous DNS pinning, socket-level peer address inspection, payload size caps, and strict redirect rules.
4. **Historical Continuity**: Safely retrieve raw snapshots from the Internet Archive Wayback Machine using monthly CDX collapsing and raw replay endpoints (`id_`).

---

## 2. Technology Stack & Dependency Matrix

| Layer | Component / Library | Version / Specification | Rationale & Responsibility |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | `FastAPI` / `Starlette` | `>= 0.110.0` | High-performance ASGI framework with native asynchronous `async`/`await` support and Pydantic validation. |
| **ASGI Server** | `Uvicorn` | `>= 0.28.0` | Lightweight, high-throughput asynchronous web server for Python. |
| **HTML Parser** | `BeautifulSoup4` + `lxml` | `bs4 >= 4.12.0`, `lxml >= 5.0.0` | C-accelerated, fault-tolerant tree parsing capable of handling malformed HTML. |
| **Async HTTP Client** | `HTTPX` + `httpcore` | `httpx 0.28.1`, `httpcore 1.0.9` | Next-generation asynchronous HTTP client supporting custom AnyIO transport backends. |
| **Asynchronous I/O** | `AnyIO` | `>= 4.0.0` | Structured concurrency abstraction providing non-blocking socket and DNS primitives. |
| **Sentence Embeddings**| `Sentence-Transformers` | `>= 2.5.0` (`all-MiniLM-L6-v2`) | Local 384-dimensional dense semantic embeddings; zero external cloud API calls. |
| **Deep Learning** | `PyTorch` | `>= 2.0.0` (CPU mode) | Execution engine for the transformer encoder with on-device tensor caching. |
| **NLP & NER** | `spaCy` | `>= 3.7.0` (`en_core_web_sm`) | Industrial-strength NLP pipeline for Named Entity Recognition and POS tagging. |
| **Frontend Framework** | `React` 18 + `Vite` | `react ^18.3.1`, `vite ^5.2.0` | Fast, reactive virtual DOM dashboard with instant HMR and Rollup production builds. |
| **Frontend Styling** | Pure Custom CSS | `frontend/src/styles.css` | Dedicated, lightweight CSS classes (`.dashboard-shell`, `.nlp-section`) with zero utility framework overhead. |

> [!NOTE]
> **Python Compatibility**: Python 3.10, 3.11, or 3.12 is strongly recommended. Python 3.14 lacks pre-built binary wheels for C-extension dependencies such as `lxml`.

---

## 3. System Architecture & Module Hierarchy

```mermaid
graph TD
    subgraph Frontend["React Frontend (frontend/src)"]
        UI_UP["UploadPage.jsx (mode: files | urls | wayback)"]
        UI_RES["ResultsPage.jsx (category filter)"]
        UI_NLP["NlpSummaryPanel.jsx (accordion & metrics)"]
        UI_API["services/comparisonService.js (AbortController)"]
    end

    subgraph API_Layer["FastAPI Layer (comparison-engine)"]
        API["api.py (/api/*)"]
    end

    subgraph Core_Engine["Core Structural Engine (src/)"]
        TREE["html_tree.py (DOM Node Hierarchy)"]
        MATCH["structural_match.py (4-Component Weighted Score)"]
        COMP["structural_compare.py (Tree Pairing)"]
        DET["change_detector.py (Change Categorization)"]
        ADAPT["result_adapter.py (Presentation Schema)"]
    end

    subgraph Network_Security["Network & Security (src/security & src/)"]
        SEC["security/ssrf_validator.py (IP Blacklists)"]
        PIN["security/pinned_transport.py (PinnedAsyncNetworkBackend)"]
        RED["security/redirect_handler.py (Safe Redirect Loop)"]
        LIVE["live_compare.py (HTML Invariant Sniffer)"]
        WAY["wayback_client.py (CDX & Replay Service)"]
    end

    subgraph NLP_Module["NLP Intelligence (src/nlp/)"]
        PIPE["nlp/pipeline.py (Orchestrator over Changes)"]
        SEM["nlp/semantic_similarity.py (MiniLM & Cache)"]
        NER["nlp/ner.py (spaCy & Regex Fallback)"]
        KW["nlp/keyword_extraction.py (Noun Chunks & POS)"]
        LOAD["nlp/model_loader.py (Thread-Safe Manager)"]
    end

    UI_UP --> UI_API
    UI_RES --> UI_API
    UI_RES --> UI_NLP
    UI_API --> API
    API --> DET
    API --> LIVE
    API --> WAY
    LIVE --> SEC
    LIVE --> RED
    RED --> PIN
    WAY --> RED
    WAY --> PIN
    LIVE --> DET
    LIVE --> PIPE
    WAY --> DET
    WAY --> PIPE
    DET --> TREE
    DET --> MATCH
    DET --> COMP
    DET --> ADAPT
    PIPE --> SEM
    PIPE --> NER
    PIPE --> KW
    PIPE --> LOAD
```

---

## 4. DOM Parsing & Tree Extraction (`html_tree.py`)

`html_tree.py` transforms raw HTML strings into structured `HTMLNode` trees:

```python
class HTMLNode:
    tag: str
    attributes: dict[str, Any]
    text: str
    children: list[HTMLNode]
    parent: weakref.ReferenceType | None
    depth: int
```

### Preprocessing and Normalization:
1. **Parser Selection**: Employs BeautifulSoup with the `lxml` parser engine for high-speed C-based parsing.
2. **Ephemeral Tag Pruning**: Elements in `{"script", "style", "noscript", "svg", "canvas", "template"}` are recursively stripped to prevent non-content diff pollution.
3. **Text Normalization**: Inner text is stripped of leading and trailing whitespace, and internal consecutive whitespace is collapsed to a single space (`" ".join(text.split())`).
4. **Attribute Sorting**: Attributes are converted to dictionaries with sorted key-value pairs; multi-value classes are lowercased and sorted alphabetically.

---

## 5. Structural Comparison Algorithms & Mathematics

---

### Weighted Node Similarity Formula (`structural_match.py`)

To align corresponding elements across revisions, `structural_match.py` computes a bipartite similarity score between $0$ and $100$:

$$\text{Score} = \text{round}\left(100 \times \left(w_1 S_{\text{tag}} + w_2 S_{\text{text}} + w_3 S_{\text{attr}} + w_4 S_{\text{children}}\right)\right)$$

Where the configured weights are:
$$w_1 = 0.35, \quad w_2 = 0.30, \quad w_3 = 0.15, \quad w_4 = 0.20$$

#### 1. Tag Similarity ($S_{\text{tag}}$)
The tag matcher supports soft semantic groupings:
$$S_{\text{tag}} = \begin{cases} 
1.0 & \text{if } \text{tag}_1 = \text{tag}_2 \\ 
0.7 & \text{if both } \in \{\text{h1}, \text{h2}, \text{h3}, \text{h4}, \text{h5}, \text{h6}\} \\ 
0.45 & \text{if both } \in \{\text{p}, \text{span}, \text{div}, \text{section}, \text{article}\} \\ 
0.0 & \text{otherwise} 
\end{cases}$$

> [!IMPORTANT]
> If $S_{\text{tag}} = 0.0$, `calculate_node_score` **immediately short-circuits and returns 0**. Unrelated tags are never paired.

#### 2. Text Similarity ($S_{\text{text}}$)
Uses Python's `difflib.SequenceMatcher`:
$$S_{\text{text}} = \text{SequenceMatcher}(\text{None}, \text{text}_1, \text{text}_2).\text{ratio}()$$
Returns $1.0$ if both text strings are empty, and $0.0$ if only one is empty.

#### 3. Attribute Similarity ($S_{\text{attr}}$)
Attribute similarity is a composite score combining key overlap and value equality:
$$S_{\text{attr}} = 0.4 \times \text{KeySim} + 0.6 \times \text{ValSim}$$
Where:
- $\text{KeySim} = \frac{|K_1 \cap K_2|}{|K_1 \cup K_2|}$ (Jaccard index of attribute key sets)
- $\text{ValSim} = \frac{\sum_{k \in K_1 \cap K_2} \mathbb{I}(\text{attr}_1[k] = \text{attr}_2[k])}{|K_1 \cap K_2|}$ (proportion of identical values among common keys)

#### 4. Children Structure Similarity ($S_{\text{children}}$)
Combines sequential tag alignment with child count parity:
$$S_{\text{children}} = 0.7 \times \text{SequenceMatcher}(\text{None}, \text{tags}_1, \text{tags}_2).\text{ratio}() + 0.3 \times \left(1 - \frac{|\text{len}_1 - \text{len}_2|}{\max(\text{len}_1, \text{len}_2)}\right)$$

#### Alignment Threshold:
$$\text{MATCH\_THRESHOLD} = 55$$
Nodes pairing with $\text{Score} \ge 55$ are established as corresponding structural candidates.

---

### Change Detection & Node Similarity (`change_detector.py`)

Once structural correspondence is determined, `change_detector.py` evaluates matched pairs for content mutations using a dedicated `node_similarity` formula:

$$\text{NodeSim} = \text{round}\left(0.85 \times \text{TextScore} + 0.15 \times \text{AttrScore}\right)$$
Where:
- $\text{TextScore} = 100 \times \text{SequenceMatcher}(\text{None}, \text{text}_1, \text{text}_2).\text{ratio}()$
- $\text{AttrScore} = 100 \times \text{SequenceMatcher}(\text{None}, \text{json}(A_1), \text{json}(A_2)).\text{ratio}()$ (JSON string of sorted attributes)

#### Classification Logic:
- **Unchanged**: $\text{text}_1 = \text{text}_2$ and $A_1 = A_2$.
- **Modified**: $\text{NodeSim} \ge \text{MODIFICATION\_THRESHOLD}$ (where $\text{MODIFICATION\_THRESHOLD} = 70$), or attribute changes on critical elements (e.g. `href` on `<a>`, `src` on `<img>`).
- **Removed**: Nodes in Version 1 with no valid match in Version 2.
- **Added**: Nodes in Version 2 with no valid match in Version 1.

---

### Frontend Presentation Adaptation (`result_adapter.py`)

`result_adapter.py` maps low-level DOM paths into clean user-facing records:
- Complete subtrees where all child elements were added or removed are condensed into high-level section cards.
- Change records contain:
  ```json
  {
    "id": 1,
    "category": "modified",
    "type": "heading",
    "element": "Heading",
    "oldValue": "Welcome",
    "newValue": "Welcome to Version 2",
    "description": "Heading text was updated.",
    "sourcePath": "/html/body[0]/h1[0]",
    "targetPath": "/html/body[0]/h1[0]",
    "similarity": 75
  }
  ```
- Summary metrics are calculated under `presentationSummary`: `total`, `added`, `removed`, `modified`.

---

## 6. Natural Language Processing & Semantic Intelligence

---

### Scope & Aggregation Architecture

> [!IMPORTANT]
> The NLP pipeline does **not** embed the entire raw HTML page as a single document. Instead, it operates over the **detected structural changes** produced by the comparison engine.

In `nlp/pipeline.py`:
1. For each item in `changes` where `category == "modified"`, the pipeline extracts `oldValue` and `newValue` and executes `analyze_text_modification`.
2. For additions and removals, it executes `analyze_text_addition` and `analyze_text_removal` to extract emerging and discontinued keywords/entities.
3. The overall metric `average_semantic_similarity` is computed as the **arithmetic mean of cosine similarities across matched modified text items only**:
   $$\text{AvgSim} = \frac{1}{N_{\text{mod}}} \sum_{i=1}^{N_{\text{mod}}} S_C(\mathbf{u}_i, \mathbf{v}_i)$$
   If no modified text elements exist, `average_semantic_similarity` is `null`.

---

### Sentence Transformer Embeddings & Cosine Mathematics

- **Model**: `sentence-transformers/all-MiniLM-L6-v2` (6 layers, 384-dimensional dense embeddings).
- **In-Memory Cache**: `_EMBEDDING_CACHE` caches computed vectors using `(id(model), model_name, text)` keys to prevent redundant neural evaluations.
- **Cosine Similarity**:
  $$S_C(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2} = \frac{\sum_{k=1}^{384} u_k v_k}{\sqrt{\sum_{k=1}^{384} u_k^2} \sqrt{\sum_{k=1}^{384} v_k^2}}$$
- The raw score is clamped to $[0.0, 1.0]$ and rounded to 4 decimal places.

#### Similarity Tiers & Exact UI Labels:
| Category Identifier | Mathematical Threshold | UI Display Label in `NlpSummaryPanel.jsx` | Semantic Interpretation |
| :--- | :--- | :--- | :--- |
| `identical` | $\ge 0.999$ | **Identical ($\ge 99.9\%$)** | No perceptible semantic shift; identical or whitespace change. |
| `high` | $\ge 0.80$ | **High Overlap ($80–99\%$)** | Minor phrasing or stylistic update; core meaning preserved. |
| `moderate` | $\ge 0.50$ | **Moderate Shift ($50–79\%$)** | Noticeable update, topic expansion, or revised terms. |
| `low` | $\ge 0.25$ | **Substantial Shift ($25–49\%$)** | Substantial rewrite with low semantic overlap. |
| `substantially_different` | $< 0.25$ | **Different ($< 25\%$)** | Completely rewritten text or replaced content. |

---

### Deterministic Fallback Similarity

If PyTorch or Sentence Transformers is unavailable, or if an unexpected exception occurs during neural inference, the engine falls back gracefully to `compute_fallback_similarity(text1, text2)`:

$$J(T_1, T_2) = \frac{|T_1 \cap T_2|}{|T_1 \cup T_2|}$$
Where $T_1$ and $T_2$ are whitespace-delimited, lowercased token sets. The result is returned with `method: "token_jaccard_fallback"`.

---

### Named Entity Recognition & Regex Fallback (`ner.py`)

- **Primary Pipeline**: spaCy `en_core_web_sm` extracts named entities (`doc.ents`).
- **Entity Matching**: Entities are keyed by `(clean_text.lower(), label)` to prevent duplicate reporting.
- **Comparison Output**:
  - `added`: Entities present in Version 2 but absent in Version 1.
  - `removed`: Entities present in Version 1 but absent in Version 2.
  - `shared`: Entities retained in both versions.
  - `by_label`: Breakdown dictionary grouping additions and removals by label (`ORG`, `DATE`, `MONEY`, `GPE`, etc.).
- **Heuristic Regex Fallback (`extract_entities_fallback`)**:
  When spaCy is missing or has no trained NER pipe, the system runs compiled regex patterns to extract:
  - `DATE`: Month names and 4-digit years (`\b(?:19|20)\d{2}\b`).
  - `MONEY`: Currency symbols (`$`, `€`, `£`, `¥`) and codes (`USD`, `EUR`, `GBP`).
  - `PERCENT`: Percent figures (`\d+%\b` or `\d+\s*percent\b`).

---

### Keyword & Noun Chunk Extraction (`keyword_extraction.py`)

1. **Noun Chunks**: Extracted first via spaCy's dependency parser (`doc.noun_chunks`). Leading stop words are stripped (e.g. `"the examination"` $\to$ `"examination"`).
2. **Token Extraction**: Individual tokens with POS tags in `{"NOUN", "PROPN", "ADJ", "VERB", "NUM"}` are extracted.
3. **Filtering Constraints**:
   - Must not be in `DEFAULT_STOP_WORDS` (150+ standard English stop words).
   - Minimum length $\ge 3$ characters (`min_length = 3`).
   - 4-digit numeric years are preserved; other pure numbers are omitted.
4. **Ordering**: Deduplicated case-insensitively while strictly preserving **first-seen document order**.
5. **Output**: Returns `added`, `removed`, and `shared` keyword lists.

---

## 7. Cybersecurity & Network Hardening Layer

---

### URL Validation & Invariant Enforcement (`ssrf_validator.py`)

Target URLs submitted to `/api/compare-urls` or `/api/wayback/*` are subjected to strict pre-validation:

1. **Protocol Restrictions**: Only `http` and `https` schemes are permitted.
2. **Credentials Rejection**: Prohibits user-information syntax (e.g., `http://user:pass@host`).
3. **Hostname Syntax**: Validated against RFC 1123 regex (labels 1–63 chars, max length 253 chars).
4. **Public IP Literals Permitted**: Direct IP literals (e.g., `http://93.184.216.34` or `http://[2606:2800:220:1:248:1893:25c8:1946]`) are parsed and **accepted if globally routable**.
5. **Prohibited Hostnames & IP Subnets**:
   - Prohibited Hostnames: `metadata.google.internal`, `metadata.internal`, `instance-data`, `localhost`.
   - Prohibited IPv4 Subnets: `0.0.0.0/8`, `10.0.0.0/8`, `100.64.0.0/10`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, `192.0.0.0/24`, `192.0.2.0/24`, `192.88.99.0/24`, `192.168.0.0/16`, `198.18.0.0/15`, `198.51.100.0/24`, `203.0.113.0/24`, `224.0.0.0/4`, `240.0.0.0/4`, `255.255.255.255/32`.
   - Prohibited IPv6 Subnets: `::/128`, `::1/128`, `64:ff9b::/96`, `100::/64`, `2001:db8::/32`, `2002::/16`, `fc00::/7`, `fe80::/10`, `ff00::/8`.
   - Obfuscated IP parsing: Detects and resolves hex (`0x7f000001`), integer (`2130706433`), and octal notation.

---

### Asynchronous DNS Pinning via AnyIO Backend (`pinned_transport.py`)

To eliminate Time-of-Check to Time-of-Use (TOCTOU) DNS rebinding attacks:

1. The HTTP client overrides `httpcore._pool._network_backend` using `PinnedAsyncNetworkBackend` (a subclass of `httpcore._backends.anyio.AnyIOBackend`).
2. When HTTPX initiates a TCP connection, `PinnedAsyncNetworkBackend.connect_tcp` executes:
   ```python
   validated_ips = await resolve_and_validate_hostname_async(host, port, timeout=timeout)
   pinned_ip = validated_ips[0]
   stream = await super().connect_tcp(host=pinned_ip, port=port, ...)
   ```
3. Because the connection is established directly to `pinned_ip`, the operating system never executes a secondary DNS lookup.
4. HTTPX and `httpcore` manage TLS Server Name Indication (SNI) and the HTTP `Host` header natively using the original hostname. Application code does not rewrite URLs or manually inject headers.

---

### Fail-Closed Socket Verification

Immediately after socket connection, the transport inspects the raw underlying network stream:
- On AnyIO async streams: `remote_addr = raw_stream.extra(anyio.abc.SocketAttribute.remote_address)`
- On sync sockets: `peer_addr = raw_sock.getpeername()`

If the physical peer address does not match `pinned_ip`, or if the stream does not support peer inspection, the stream is closed immediately and `PeerVerificationError` is raised (fail-closed).

---

### Safe Manual Redirect Loop & RFC 9110 Rewriting (`redirect_handler.py`)

Automatic client redirects are disabled (`follow_redirects=False`). Manual redirect handling executes under strict invariants:
- Maximum 5 redirect hops (`DEFAULT_MAX_REDIRECTS = 5`).
- Destination URL re-validation: `validate_target_url(new_url, resolve_dns=False)` is executed prior to every hop.
- Insecure downgrade prevention: Redirects from HTTPS to HTTP raise `RedirectSecurityError`.
- Circular redirect detection: Visited URLs are tracked in a set.
- Sensitive header stripping: If `not is_same_origin(current_url, new_url)`, `Authorization`, `Cookie`, and `Proxy-Authorization` headers are stripped.
- **RFC 9110 Method Rewriting**:
  - Status 303 (See Other): Converts method to `GET`, discards body, and strips `Content-Length` and `Content-Type`.
  - Status 301 / 302: Rewrites non-GET/HEAD methods to `GET` and discards body.
  - Status 307 / 308: Preserves method and body.

---

### HTML Content Invariants & Sniffing Fallback (`live_compare.py`)

Before fetched content is passed to the comparison engine, `validate_html_response` enforces:
1. Status code must be `200 OK` (non-200 raises `LiveFetchError`).
2. Body must not be empty.
3. Media type validation:
   - Explicitly rejects `application/json`, `application/pdf`, `application/xml`, `text/xml`, `image/*`, `audio/*`, `video/*`, `font/*`.
   - Standard HTML: `text/html`, `application/xhtml+xml`.
   - If Content-Type is missing or non-standard, the first 2048 bytes are sniffed for `<html` or `<!doctype html`.
4. Document structure: The parsed document must contain an `<html>` root element.

---

## 8. Wayback Machine Historical Integration (`wayback_client.py`)

---

### Monthly CDX Snapshot Discovery & Truncation Detection

To discover historical captures of a target URL, `discover_wayback_snapshots` dispatches a GET request to `https://web.archive.org/cdx/search/cdx`:

```python
params = {
    "url": request.url,
    "output": "json",
    "fl": "timestamp,original,mimetype,statuscode,length",
    "filter": ["statuscode:200", "mimetype:text/html"],
    "collapse": "timestamp:6",
    "limit": "-51",
}
```

- **Monthly Collapsing (`collapse: "timestamp:6"`)**: The CDX server groups captures by `YYYYMM`, returning at most one snapshot per month.
- **Truncation Detection (`limit: "-51"`)**: Requests the latest 51 monthly captures in reverse order. If 51 items are returned, `is_limited` is set to `True`, and the results are capped at 50 captures.
- **Allowed Host Enforcement**: Pre-hop hostname validation ensures all requests and redirects target `web.archive.org` on HTTPS port 443.

---

### Point Snapshot Verification

Before fetching raw HTML captures, `verify_snapshot_timestamp` issues a point query to the CDX API with `limit=1` and `from=timestamp`, `to=timestamp`. It verifies that:
1. The exact 14-digit timestamp exists in the archive.
2. The archived HTTP status code was 200.
3. The archived MIME type was HTML.
4. The CDX original URL is valid and safe.

---

### Raw Replay Retrieval & Fallback Redirect Rejection

Raw HTML captures are fetched using the raw replay URL format:
$$\text{Replay URL} = \text{https://web.archive.org/web/}\{\text{timestamp}\}\text{id\_}/\{\text{original\_url}\}$$

> [!NOTE]
> The `id_` flag instructs the Wayback replay engine to serve the archived HTML verbatim, preventing injection of the Wayback toolbar JavaScript banner.

#### Fallback Redirect Rejection:
The client extracts the timestamp from the beginning of the resolved URL path:
```python
PATH_REPLAY_TIMESTAMP_REGEX = re.compile(r"^/web/([0-9]{14})id_/")
```
If the Wayback server redirects to a nearest-capture timestamp rather than the exact requested timestamp, `FallbackRedirectError` is raised to prevent comparing a corrupted historical state.

---

### Error Hierarchy & HTTP Status Code Mapping

Exceptions in `wayback_client.py` and `live_compare.py` map deterministically to FastAPI HTTP status codes:

| Backend Exception | HTTP Status Code | Description / User Error Message |
| :--- | :---: | :--- |
| `InvalidURLError`, `BlockedIPError`, `InvalidWaybackURLError` | `400 Bad Request` | Security violation: URL syntax error or private IP address. |
| `SnapshotNotFoundError` | `404 Not Found` | Snapshot for specified timestamp not found in CDX index. |
| `FallbackRedirectError` | `409 Conflict` | Wayback redirected to a fallback/nearest timestamp capture. |
| `ResourceLimitError` (Payload > 10 MB) | `413 Payload Too Large` | Webpage response exceeded maximum allowed 10 MB limit. |
| `HTMLValidationError` (Unsupported MIME) | `415 Unsupported Media Type`| Non-HTML content-type (JSON, PDF, image, etc.). |
| `HTMLValidationError` (Malformed / No `<html>`) | `422 Unprocessable Entity` | Document is empty or missing valid `<html>` root. |
| `WaybackVerificationError` | `422 Unprocessable Entity` | Snapshot record in CDX has non-200 status or non-HTML MIME. |
| `OffHostRedirectError`, `DNSResolutionError`, `WaybackCDXError` | `502 Bad Gateway` | Upstream service or unauthorized redirect error. |
| `ResourceLimitError` (Deadline exceeded) | `504 Gateway Timeout` | Request exceeded 20.0s overall deadline. |

---

## 9. API Specification & Data Schemas (`api.py`)

All API routes are served under the `/api` prefix.

### 1. `POST /api/compare`
Compares two uploaded multipart form-data HTML files.
- **Request**: `version1: UploadFile`, `version2: UploadFile` (must have `.html` or `.htm` extension).
- **Response**: Adapted JSON result payload (`version1`, `version2`, `changes`, `presentationSummary`, `engineSummary`).

### 2. `POST /api/compare-urls`
Concurrently fetches two live URLs and returns structural + NLP comparison.
- **Request Body**:
  ```json
  {
    "url1": "https://example.com",
    "url2": "https://www.iana.org/domains/reserved"
  }
  ```
- **Response**: Adapted JSON payload enriched with `nlpAnalysis` object.

### 3. `GET /api/wayback/snapshots`
Discovers historical monthly captures from the CDX API.
- **Query Parameters**:
  - `url` (string, required): Webpage target URL.
  - `from_year` (int, optional): Earliest year (1996–2099).
  - `to_year` (int, optional): Latest year (1996–2099).
- **Response**:
  ```json
  {
    "url": "https://www.iana.org",
    "total_returned": 24,
    "is_limited": false,
    "collapse": "monthly",
    "snapshots": [
      {
        "timestamp": "20230515120000",
        "datetime": "2023-05-15T12:00:00Z",
        "display_date": "May 15, 2023 12:00 UTC",
        "original_url": "https://www.iana.org",
        "status_code": 200,
        "mimetype": "text/html"
      }
    ]
  }
  ```

### 4. `POST /api/wayback/compare`
Fetches and compares two historical captures.
- **Request Body**:
  ```json
  {
    "url": "https://www.iana.org",
    "timestamp1": "20210515120000",
    "timestamp2": "20230515120000"
  }
  ```
- **Response**: Adapted JSON payload enriched with `nlpAnalysis`.

### CORS Configuration:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```

---

## 10. Frontend Architecture & State Machine

The frontend is a single-page React application structured as follows:

- **State Isolation**: Mode switching between `'files' | 'urls' | 'wayback'` maintains strictly separated input state.
- **Discovery Invalidation (`UploadPage.jsx`)**: Modifying `waybackUrl`, `fromYear`, or `toYear` calls `invalidateWaybackDiscovery()`. This increments a sequence ref (`discoverySeqRef`), aborts active requests via `discoveryAbortControllerRef`, and resets discovered snapshots and dropdown selections.
- **Results View (`ResultsPage.jsx`)**:
  - Section 01: `ChangeSummary.jsx` displays overview counts and narrative summary.
  - Section 02 (when `hasNlp` is true): `NlpSummaryPanel.jsx` displays semantic similarity metrics, similarity distribution cards, top keyword shifts, and an accordion of individual modified text items.
  - Section 03 (or Section 02 when `hasNlp` is false): `ChangeFilters.jsx` filters changes by `change.category` (`all`, `added`, `removed`, `modified`). Each change card renders side-by-side Before/After diffs.
- **API Service (`services/comparisonService.js`)**: Encapsulates all backend HTTP calls using native `fetch` with `AbortController` signal forwarding.

---

## 11. Verification Evidence & Automated Test Matrix

The complete test suite contains **291 passing automated tests** in `comparison-engine/tests`:

```bash
cd comparison-engine
pytest tests/ -v
```

```text
======================= 291 passed in 19.31s =======================
```

| Test File | Test Count | Verified Technical Behaviors |
| :--- | :---: | :--- |
| `test_html_tree.py` | 5 | DOM tree construction, whitespace normalization, script/style/svg tag pruning. |
| `test_structural_compare.py` | 5 | Bipartite tree alignment, weighted score formulas, modification thresholds. |
| `test_security.py` / `test_url_validator.py` | 56 | URL syntax parsing, IPv4/IPv6 literals, private/loopback/cloud metadata IP blocking. |
| `test_pinned_transport.py` | 82 | AnyIO backend DNS pinning, socket peer verification, redirect hop limits, deadline enforcement. |
| `test_nlp.py` | 47 | MiniLM embedding vectors, cosine similarity calculation, tier categorization, NER regex fallback, keywords. |
| `test_live_compare.py` | 24 | Concurrent web fetching, HTML content-type validation, 2048-byte sniffing fallback, error bubbling. |
| `test_wayback.py` | 48 | CDX monthly collapsing (`timestamp:6`), snapshot point verification, raw replay fetching (`id_`). |
| `test_api_wayback.py` | 24 | FastAPI route contracts, parameter validation, HTTP status code error mapping. |

---

## 12. Project Scope & Operational Boundaries

### Implemented in the Current Project
- **Three Comparison Modes**: HTML file upload (`files`), live URL comparison (`urls`), and historical Wayback comparison (`wayback`).
- **DOM / Structural Change Detection**: DOM tree building, tag pruning, and bipartite matching with weighted similarity scoring.
- **Categorized Change Reporting**: Explicit classification of additions, removals, and modifications across semantic elements (`Heading`, `Paragraph`, `Link`, `Button`, `Page title`).
- **Granular NLP Analysis of Modified Text**: Sentence Transformers (`all-MiniLM-L6-v2`) computing cosine similarity across matched modified text items, with deterministic token Jaccard fallback.
- **Entity and Keyword Dynamics**: spaCy NER identifying added, removed, and shared entities (`ORG`, `PERSON`, `GPE`, `DATE`, `MONEY`, `PERCENT`) with regex fallback, alongside noun chunk and keyword extraction.
- **SSRF-Aware Network Hardening**: Asynchronous DNS pinning using a custom `httpcore` AnyIO backend, private IP address blocking (RFC 1918, RFC 3927, loopback, cloud metadata), fail-closed socket peer verification, 10 MB payload limits, and 20s deadlines.
- **Interactive Web Interface**: Single-page React dashboard built with Vite and custom CSS (`styles.css`), backed by a Python FastAPI REST API.

---

### Outside Current Scope / Operational Limitations
To ensure academic honesty, the following capabilities are explicitly outside the current implementation scope:
- **No Client-Side JavaScript Execution**: The engine does not execute JavaScript. Single-Page Applications (SPAs) that require client-side execution without Server-Side Rendering (SSR) expose only initial skeleton HTML.
- **No Headless Browser Automation**: The application uses direct HTTP streaming clients; it does not drive a browser instance (such as Puppeteer, Playwright, or Selenium) for live comparison.
- **No Visual / Pixel Screenshot Diffing**: The tool tracks content and DOM hierarchy. It does not measure rendered pixel differences such as CSS animations, font smoothing, or layout positioning that do not alter DOM attributes.
- **No Recursive Domain Crawling**: The tool compares specific individual documents or URLs; it does not crawl an entire website domain recursively.
- **No Multi-Page Automated Crawling**: It operates on single-page pairs, not automated directory trees.
- **No Authentication or Cookie Sessions**: It does not support login-gated pages, paywalled content, or cookie-based sessions.
- **No Guaranteed Archive Availability**: Snapshot availability is subject to whether the Internet Archive has crawled and indexed the target page.
- **No Background Monitoring / Cron Alerting**: It performs on-demand comparisons; it does not continuously poll websites in the background for future changes.

---

### Project Scope — Presentation Summary
*(Suitable for project reports, viva slides, and formal presentations)*

> **System Overview**: Historical Webpage Comparison is a full-stack automated intelligence system that tracks structural, textual, and semantic revisions in web pages. The platform operates across three modes: offline HTML file comparison, live URL comparison, and historical Internet Archive snapshot comparison.
>
> **Core Architecture**: The engine parses raw HTML into Document Object Model trees, strips non-content tags, aligns corresponding elements using a 4-component weighted structural matcher, and calculates on-device semantic similarity using Sentence Transformers. The network layer is hardened against Server-Side Request Forgery (SSRF) and DNS rebinding attacks through asynchronous socket pinning.
>
> **Target Workload**: The application is designed for publicly accessible, server-rendered HTML pages, legal disclosures, policy documents, and archived captures. It evaluates on-demand comparisons for single-page pairs within a 10 MB streaming ceiling.
>
> **Key Distinctions**: Live comparison evaluates real-time web responses, whereas historical comparison queries Wayback CDX records. Semantic similarity is evaluated specifically across matched modified text items to detect meaning drift, rather than whole-page document classification.
>
> **Why It Is Useful**: It reduces superficial diff noise caused by whitespace, attribute ordering, and minor markup changes by matching DOM node hierarchies, helping reviewers focus on meaningful content additions, removals, and text updates.

---

### 30-Second Summary for Faculty / HOD
> "Our project is an automated webpage revision tracking platform that bridges the gap between syntactic line diffs and human semantic understanding. It takes two versions of a webpage—from local files, live URLs, or historical Wayback snapshots—builds a normalized DOM tree, and uses a weighted scoring algorithm to detect added, removed, and modified elements. For modified text, it runs an on-device Sentence Transformer to measure whether wording revisions actually changed the meaning, while our network layer mitigates SSRF and DNS rebinding risks through IP blacklisting, custom AnyIO socket pinning, and fail-closed peer-address verification. It focuses on server-rendered HTML without client-side JavaScript execution."

---

*This technical documentation is part of the official project specification suite for Historical Webpage Comparison.*
