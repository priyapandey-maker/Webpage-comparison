# Historical Webpage Comparison — End-User Guide & Tutorial

Welcome to the **Historical Webpage Comparison** user guide. This document provides clear, step-by-step instructions for non-technical users, evaluators, compliance officers, and researchers on how to use the application to detect and analyze changes in web content over time.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Project Scope & Limitations](#2-project-scope--limitations)
   - [Implemented in the Current Project](#implemented-in-the-current-project)
   - [Not Currently Implemented / Outside Current Scope](#not-currently-implemented--outside-current-scope)
   - [Project Scope — Presentation Summary](#project-scope--presentation-summary)
   - [30-Second Summary for Faculty / HOD](#30-second-summary-for-faculty--hod)
3. [The Three Comparison Modes](#3-the-three-comparison-modes)
   - [Mode 1: Upload HTML Files (Mode `files`)](#mode-1-upload-html-files-mode-files)
   - [Mode 2: Live URL Comparison (Mode `urls`)](#mode-2-live-url-comparison-mode-urls)
   - [Mode 3: Wayback Historical Comparison (Mode `wayback`)](#mode-3-wayback-historical-comparison-mode-wayback)
4. [Supported Websites and Demonstration Examples](#4-supported-websites-and-demonstration-examples)
   - [Compatibility Criteria for Live Websites](#compatibility-criteria-for-live-websites)
   - [Requirements for Wayback Historical Comparison](#requirements-for-wayback-historical-comparison)
   - [Demonstration Test Catalogue](#demonstration-test-catalogue)
   - [Exact Verified Demonstration Pairs](#exact-verified-demonstration-pairs)
5. [Input Rules, Restrictions & Security Warnings](#5-input-rules-restrictions--security-warnings)
6. [Understanding Comparison Results](#6-understanding-comparison-results)
   - [Section 01: Change Overview](#section-01-change-overview)
   - [Section 02: Semantic Analysis of Modified Text (NLP)](#section-02-semantic-analysis-of-modified-text-nlp)
   - [Section 03: Detected Changes Feed & Category Filters](#section-03-detected-changes-feed--category-filters)
7. [Realistic Walkthrough Scenarios](#7-realistic-walkthrough-scenarios)
8. [Frequently Asked Questions (FAQ)](#8-frequently-asked-questions-faq)

---

## 1. Introduction

The **Historical Webpage Comparison** platform enables users to compare two versions of a webpage to see exactly what changed in content, structure, and meaning.

### What the Application Detects:
- **Structural Additions**: Newly added buttons, links, paragraphs, headings, or list items.
- **Structural Removals**: Content elements or navigation links that have been deleted.
- **Text & Attribute Modifications**: Changes in headings, body copy, link destinations (`href`), or image sources (`src`).
- **Semantic Meaning Drift (NLP)**: Machine-learning analysis measuring whether wording edits altered the core message or meaning across matched modified text items.
- **Named Entity Updates**: Tracking companies, people, dates, monetary amounts, and percentages that appeared or disappeared.
- **Keyword Dynamics**: Top terms that were introduced or discontinued.

---

## 2. Project Scope & Limitations

### Implemented in the Current Project
- **HTML File Upload Comparison (`files`)**: Direct offline diffing of two uploaded static `.html` files.
- **Live URL Comparison (`urls`)**: Concurrent streaming retrieval and comparison of two live internet web pages over secure transport.
- **Wayback Machine Integration (`wayback`)**: Discovery of historical monthly snapshots via the Internet Archive CDX Server API and comparison using raw snapshot replay (`id_`).
- **DOM / Structural Change Detection**: Conversion of HTML to normalized DOM node trees, tag pruning, and bipartite matching with weighted similarity scoring.
- **Categorized Change Reporting**: Explicit classification of additions, removals, and modifications across semantic elements (`Heading`, `Paragraph`, `Link`, `Button`, `Page title`).
- **Granular NLP Analysis of Modified Text**: Sentence Transformers (`all-MiniLM-L6-v2`) computing cosine similarity across matched modified text items, with deterministic token Jaccard fallback.
- **Entity and Keyword Dynamics**: spaCy NER identifying added, removed, and shared entities (`ORG`, `PERSON`, `GPE`, `DATE`, `MONEY`, `PERCENT`) with regex fallback, alongside noun chunk and keyword extraction.
- **SSRF-Aware Network Hardening**: Asynchronous DNS pinning using a custom `httpcore` AnyIO backend, private IP address blocking (RFC 1918, RFC 3927, loopback, cloud metadata), fail-closed socket peer verification, 10 MB payload limits, and 20s deadlines.
- **Interactive Web Interface**: Single-page React dashboard built with Vite and custom CSS (`styles.css`), backed by a Python FastAPI REST API.

---

### Not Currently Implemented / Outside Current Scope
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

## 3. The Three Comparison Modes

### Mode 1: Upload HTML Files (Mode `files`)

*Best for: Comparing static HTML files saved on your computer, archived reports, or offline templates.*

1. Click the **Upload HTML Files** tab.
2. Under **Previous Version (Version 1)**, drag and drop an `.html` or `.htm` file, or click to open your system file picker.
3. Under **Current Version (Version 2)**, drag and drop the newer `.html` or `.htm` file.
4. Click **Compare Versions**.
5. The comparison runs offline locally. The dashboard loads showing additions, removals, and modifications.

> [!NOTE]
> Mode 1 runs structural DOM comparison only. Because files are local and offline, the NLP semantic intelligence panel is omitted to provide instant results.

---

### Mode 2: Live URL Comparison (Mode `urls`)

*Best for: Comparing two active websites on the internet (e.g., staging vs. production, or competitor pages).*

1. Click the **Live URL Comparison** tab.
2. Enter the first URL in the **Previous Version URL** field (e.g., `https://example.com`).
3. Enter the second URL in the **Current Version URL** field (e.g., `https://www.iana.org/domains/reserved`).
4. Click **Compare Live URLs**.
5. The backend concurrently fetches both pages over a secure, DNS-pinned connection, strips ephemeral scripts/styles, runs structural diffing, and executes the NLP semantic analysis pipeline.

---

### Mode 3: Wayback Historical Comparison (Mode `wayback`)

*Best for: Tracking how a specific public website evolved across years using the Internet Archive Wayback Machine.*

1. Click the **Wayback Historical Comparison** tab.
2. Enter the target web address in the **Website URL** field (e.g., `https://www.iana.org`).
3. *(Optional)* Specify a date range in the **From Year** and **To Year** fields (valid years: 1996 to 2099; `from_year` must be $\le$ `to_year`).
4. Click **Find Snapshots**.
   - The application queries the Internet Archive CDX Server API using **monthly collapsing** (`timestamp:6`), returning up to 50 curated captures.
   - If more than 50 captures exist, an informational badge indicates that results are capped at the latest 50 monthly captures (`is_limited = True`).
5. Two dropdown menus appear:
   - **Select Snapshot 1 (Older)**: Choose an earlier capture date.
   - **Select Snapshot 2 (Newer)**: Choose a later capture date.
   - *Note: You cannot select identical timestamps.*
6. Click **Compare Historical Snapshots**.
7. The system retrieves raw HTML captures (using the `id_` raw replay flag to eliminate the Wayback navigation banner) and displays both structural diffs and NLP semantic metrics.

> [!IMPORTANT]
> **Discovery Invalidation**: If you modify the target URL or change the From/To year inputs after discovering snapshots, active discovery requests are aborted via `AbortController`, and the snapshot dropdowns automatically reset to prevent state contamination. Click **Find Snapshots** again to fetch updated captures.

---

## 4. Supported Websites and Demonstration Examples

---

### Compatibility Criteria for Live Websites
Live URL comparison is intended for publicly accessible websites that satisfy the following operational requirements:
1. **Protocol**: Must use standard `http://` or `https://`.
2. **Server-Rendered HTML**: Must return parseable HTML markup (`text/html` or `application/xhtml+xml`) containing a valid `<html>` document root.
3. **No Authentication or Sessions**: Must be public; pages behind login gates, paywalls, or requiring session cookies are not supported.
4. **No Anti-Bot or CAPTCHA Gates**: Must not be protected by Cloudflare Turnstile, Cloudflare Under Attack mode, Akamai Bot Manager, or similar anti-bot systems that block automated HTTP clients.
5. **Resource Limits**: Response body must be under 10 Megabytes and must respond within the 20-second connection deadline.

> [!CAUTION]
> Compatibility depends on the target server's live HTTP response. Some websites return HTTP 403 Forbidden to automated User-Agents (for example, `umich.edu`), even if they appear accessible in desktop web browsers.

---

### Requirements for Wayback Historical Comparison
Wayback Machine comparison additionally requires:
1. **CDX Indexing**: The target website must have been crawled and indexed by the Internet Archive CDX API.
2. **Usable Capture Count**: There must be at least two usable captures with HTTP 200 status and HTML media type.
3. **Valid HTML Replay**: The archived HTML must be retrievable via `web.archive.org/web/{timestamp}id_/{url}` without redirecting to a different timestamp (`FallbackRedirectError`).
4. **Security Policy**: All replay requests must strictly reside on `web.archive.org` on HTTPS port 443.

---

### Demonstration Test Catalogue

The following table records candidate websites investigated using the actual comparison engine and network client:

| Website | Live URL | Live Suitability | Wayback Availability | Historical Captures Checked | Purpose in Demo | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **IANA Home** | `https://www.iana.org` | High; clean HTML, fast response (6.2 KB) | High; 24 monthly captures (2022–2023) | `20220128084535` vs `20231231222555` | Mode 3 Historical comparison & NLP | **Verified working** |
| **IANA Reserved Domains** | `https://www.iana.org/domains/reserved` | High; semantic tables & lists (10.9 KB) | High | CDX indexed | Mode 2 Live pair target | **Verified working** |
| **Example Domain** | `https://example.com` | High; lightweight static HTML (577 bytes) | High; 24 monthly captures (2022–2023) | Minimal content changes over time | Mode 2 Live pair source | **Verified working** |
| **Python.org** | `https://www.python.org` | High; rich content, news (52 KB) | High; 24 monthly captures (2022–2023) | `20220131220219` vs `20231231231051` | Content-rich live & historical comparison | **Verified working** |
| **MIT Homepage** | `https://www.mit.edu` | High; articles and spotlight links (47.7 KB) | High; 24 monthly captures (2022–2023) | `20220131213846` vs `20231231132448` | Academic portal comparison | **Verified working** |
| **Wikipedia Portal** | `https://www.wikipedia.org` | High; multilingual portal (122 KB) | High; extensive historical archive | Not yet compared in engine | High-volume portal comparison | **Live verified; Wayback needs testing** |
| **MDN Web Docs** | `https://developer.mozilla.org/en-US/` | Moderate; documentation home (116 KB) | Moderate; frequent Jamstack layout updates | Not yet compared in engine | Technical documentation diff | **Live verified; Wayback needs testing** |
| **University of Michigan** | `https://umich.edu` | **Unsuitable**; returns HTTP 403 Forbidden to automated requests | CDX indexed | Blocked at transport | Demonstrating anti-bot / 403 handling | **Not suitable (HTTP 403)** |

---

### Exact Verified Demonstration Pairs

For live presentations and evaluations, use these verified test pairs:

#### Pair A: HTML File Upload (`files`)
- **Source Files**:
  - Version 1: `comparison-engine/examples/version1.html`
  - Version 2: `comparison-engine/examples/version2.html`
- **Verification Status**: **Verified working**
- **Expected Results**:
  - Total Changes: `5`
  - Added: `1` (New button labeled `"Start"`)
  - Removed: `0`
  - Modified: `4` (Link destination `/old` $\to$ `/new`, Heading `"Welcome"` $\to$ `"Welcome to Version 2"`, Paragraph `"Original text."` $\to$ `"Updated text."`, Page title `"Demo Page"` $\to$ `"Updated Demo Page"`).

> [!NOTE]
> Keep this separate from `test-files/mini project`, which contains a different test fixture pair producing 21 changes (8 additions, 1 removal, 12 modifications).

#### Pair B: Live Website Comparison (`urls`)
- **Input URLs**:
  - Version 1: `https://example.com`
  - Version 2: `https://www.iana.org/domains/reserved`
- **Verification Status**: **Previously verified**
- **Expected Results**:
  - Total Changes: `10`
  - Added: `5`
  - Removed: `1`
  - Modified: `4`
  - NLP Semantic Analysis: Displays moderate semantic overlap with keyword and entity tags.

#### Pair C: Historical Wayback Comparison (`wayback`)
- **Target URL**: `https://www.iana.org`
- **Selected Timestamps**:
  - Snapshot 1: `20220128084535` (Jan 28, 2022 08:45 UTC)
  - Snapshot 2: `20231231222555` (Dec 31, 2023 22:25 UTC)
- **Verification Status**: **Freshly verified**
- **Exact Results**:
  - Total Changes: `6`
  - Added: `0`
  - Removed: `1` (Removed text element)
  - Modified: `5` (Updated headings and navigational links)
  - Average Semantic Similarity: `44.0%` (Substantial Shift, score `0.4399`)
  - Summary: *"Analyzed 5 text modifications with an average semantic similarity of 44.0%. Found 1 text removal."*

#### Pair D: Security Defense Demonstration
- **Test 1 (Loopback Address)**: `http://127.0.0.1:8000`
  - *Expected Rejection*: Immediate HTTP 400 error: `"Access to 127.0.0.1 is forbidden: Loopback address (127.0.0.1)."`.
- **Test 2 (Prohibited Hostname)**: `http://localhost:8000`
  - *Expected Rejection*: Immediate HTTP 400 error: `"Access to prohibited hostname 'localhost' is blocked."`.
- **Test 3 (Cloud Metadata Address)**: `http://169.254.169.254/latest/meta-data/`
  - *Expected Rejection*: Immediate HTTP 400 error: Link-local address forbidden (`169.254.0.0/16`).
- **Test 4 (Public IP Literal - Permitted)**: `http://93.184.216.34`
  - *Expected Result*: Validated successfully by the URL validator and accepted for connection.

---

## 5. Input Rules, Restrictions & Security Warnings

To protect against cyber threats and ensure reliable comparison, the system enforces strict input and network validation rules:

### 1. Supported URL Formats
- **Permitted Schemes**: Only `http://` and `https://` are permitted. Schemes such as `file://`, `ftp://`, or `gopher://` are rejected.
- **Hostnames**: Standard RFC 1123 domain names (e.g., `example.com`, `docs.python.org`) are supported.
- **Public IP Literals**: Public, globally routable IP addresses (e.g., `http://93.184.216.34`) **are accepted**.
- **No Embedded Credentials**: URLs with user credentials (e.g., `http://admin:secret@site.com`) are forbidden.

### 2. Blocked Private Networks (SSRF Protection)
The system blocks requests targeting internal or private network infrastructure:
- **Loopback Addresses**: `127.0.0.0/8`, `localhost`, `::1`
- **Private Subnets (RFC 1918)**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- **Link-Local & Cloud Metadata**: `169.254.0.0/16`, `fe80::/10`, `metadata.google.internal`, `instance-data`
- **Multicast & Reserved Subnets**: `224.0.0.0/4`, `240.0.0.0/4`, `fc00::/7`

Attempting to query these destinations triggers an immediate security error (e.g., `Access to 127.0.0.1 is forbidden: Loopback address (127.0.0.1)`).

### 3. Accepted HTML Content & Limits
- **Status Code**: Target servers must return `HTTP 200 OK`.
- **Response Content-Type**: Standard HTML MIME types (`text/html`, `application/xhtml+xml`) are accepted. Explicitly non-HTML formats (`application/json`, `application/pdf`, `application/xml`, images, audio, video) are rejected.
- **HTML Sniffing**: If a server returns an ambiguous or missing Content-Type header, the first 2048 bytes are sniffed for `<html` or `<!doctype html`.
- **Payload Size Ceiling**: Webpages larger than 10 Megabytes are aborted to prevent memory exhaustion.
- **Timeout Ceiling**: Requests that stall or take longer than 20 seconds are terminated (`504 Gateway Timeout`).

---

## 6. Understanding Comparison Results

When a comparison completes, the **Results Page** presents structured insights divided into clear sections.

---

### Section 01: Change Overview
The top section displays high-level metrics:
- **Total Changes**: Sum of all meaningful differences detected.
- **Added**: Count of newly introduced elements.
- **Removed**: Count of deleted elements.
- **Modified**: Count of altered elements.
- **Change Summary Narrative**: An automated natural-language summary explaining what changed in simple terms.

---

### Section 02: Semantic Analysis of Modified Text (NLP)

*(Rendered only in Live URL and Wayback modes when modified text elements are present.)*

> **Notice**: *"Applies strictly to matched text modifications; does not reflect whole-webpage similarity."*

The NLP panel provides machine-learning intelligence:
1. **Average Semantic Similarity**: The mean cosine similarity calculated across all matched modified text items.
2. **Analysis Metric Cards**: Counts of modified text items, new text items, and removed text items analyzed.
3. **Semantic Change Summary**: A concise paragraph summarizing the semantic severity of edits.
4. **Similarity Distribution Cards**: Breakdown of modified items into 5 qualitative categories:
   - **Identical ($\ge 99.9\%$)**: Text with no perceptible semantic change.
   - **High Overlap ($80–99\%$)**: Minor rephrasings or stylistic updates.
   - **Moderate Shift ($50–79\%$)**: Meaningful updates or topic expansion.
   - **Substantial Shift ($25–49\%$)**: Major revisions with low semantic overlap.
   - **Different ($< 25\%$)**: Completely rewritten content.
5. **Key Content Terms**:
   - **Key Added Terms** (prefixed with `+`): Important nouns or phrases introduced in the new version.
   - **Key Removed Terms** (prefixed with `-`): Vocabulary removed from the original text.
6. **Modified Text Item Details (Accordion)**: Click any modified item to expand its individual Before $\to$ After text comparison, similarity percentage, category badge, explanation, and detected named entities (dates, companies, monetary amounts).

---

### Section 03: Detected Changes Feed & Category Filters

*(Rendered as Section 02 when NLP data is absent.)*

The changes feed lists every structural difference:
- **Filter Tabs**: Click **All**, **Added**, **Removed**, or **Modified** to filter the cards in real time using `change.category`. Each button displays a count badge.
- **Before / After Diff Cards**:
  - Element label (e.g., `Heading`, `Paragraph`, `Link`, `Button`, `Page title`).
  - Left column (`BEFORE`): Shows the original text and attributes.
  - Right column (`AFTER`): Shows the updated text and attributes.
  - Description: Clear explanation of what changed (e.g., *"Link updated (href: /new)"*).
- **Back Navigation**: Click **← Compare another pair** at the top to return to the input screen.

---

## 7. Realistic Walkthrough Scenarios

### Scenario A: Terms of Service Revisions
- **Goal**: A legal analyst wants to see how a company modified its Privacy Policy.
- **Action**: In Live URL mode, input the previous archived policy URL and the current policy URL.
- **Result**:
  - The NLP panel highlights that semantic similarity dropped to **Moderate Shift (68.4%)**.
  - The Named Entities breakdown shows that a specific date (`"January 1, 2021"`) was removed and replaced with (`"March 15, 2024"`).
  - An added paragraph card reveals an updated data-retention clause.

### Scenario B: Competitor Product Updates
- **Goal**: An e-commerce manager wants to monitor a competitor's pricing table over the last two years.
- **Action**: In Wayback mode, enter the product URL and set the range from `2022` to `2024`. Select a 2022 monthly snapshot and a 2023 monthly snapshot.
- **Result**:
  - The overview shows modifications and additions.
  - The NLP entity breakdown isolates updated monetary amounts (e.g., `"$49/mo"` $\to$ `"$79/mo"`).
  - The structural diff shows a new `Button` labeled `"Subscribe Now"`.

---

## 8. Frequently Asked Questions (FAQ)

#### Q: Why does Mode 1 not show the Semantic Analysis panel?
> **A**: Mode 1 is designed as an ultra-fast, local, offline file diff tool. The NLP pipeline requires running transformer models and is reserved for Live URL and Historical comparisons where semantic intelligence is most critical.

#### Q: Can I compare pages from single-page web applications (like React or Vue)?
> **A**: Yes, provided the server returns initial HTML content. However, the system does not execute client-side JavaScript. If a web application renders entirely through client-side JavaScript without Server-Side Rendering (SSR), the comparison will only see the initial skeleton HTML.

#### Q: Why did my Wayback snapshot request return an HTTP 409 Conflict error?
> **A**: The Wayback Machine occasionally redirects to a different timestamp if the requested snapshot is missing or corrupted. The system strictly rejects fallback redirects to ensure that comparisons accurately reflect the exact historical date you selected.

#### Q: Why was my internal IP address rejected?
> **A**: For cybersecurity reasons, the system blocks access to private subnets, loopback addresses (`127.0.0.1`), and cloud metadata services to prevent Server-Side Request Forgery (SSRF).

---

*This user guide is part of the official project documentation suite for Historical Webpage Comparison.*
