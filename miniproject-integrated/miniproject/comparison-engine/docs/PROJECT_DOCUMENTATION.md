# Project Documentation – Member 2

## 1. Objective
The objective is to compare two historical versions of a webpage and produce an interpretable record of structural and textual changes.

## 2. Input
Two HTML files are required: Version 1 (older snapshot) and Version 2 (newer snapshot).

## 3. Processing Modules
### html_tree.py
Uses BeautifulSoup to parse HTML, cleans text, creates node fingerprints, builds a hierarchical tree, and saves it as JSON.

### structural_match.py
Calculates similarity using normalized text, attributes, child structure, and tag information. It proposes corresponding nodes across versions.

### structural_compare.py
Flattens trees into paths and generates structural comparison information for matched nodes.

### change_detector.py
Uses the trees and structural matches to identify additions, removals, and modifications. Similarity thresholds help distinguish modifications from unrelated nodes.

### run_pipeline.py
Provides one repeatable command that coordinates tree generation, matching, comparison, and change detection.

## 4. Output Files
| File | Purpose |
|---|---|
| tree_v1.json | Structured representation of older HTML |
| tree_v2.json | Structured representation of newer HTML |
| structural_matches.json | Probable node correspondences |
| comparison.json | Structural comparison data |
| changes.json | Detected additions, removals, and modifications |
| run_summary.json | Compact count summary |

## 5. Improvement Work
- Added a single command-line workflow.
- Added input-file validation.
- Added a dedicated output directory.
- Added a run summary for quick inspection.
- Removed the bundled virtual environment from the deliverable.
- Added an example pair of HTML snapshots.
- Added setup and limitation documentation.

## 6. Viva Explanation
The system does not compare raw HTML character by character. First, each page is converted into a structured tree. Nodes are then matched using similarity measures such as tag, text, attributes, and child structure. Finally, matched nodes are compared to classify changes as additions, removals, or modifications. This reduces false differences caused by formatting and whitespace.

## 7. Future Scope
- JavaScript-rendered page capture using a browser automation tool.
- Screenshot and visual-layout comparison.
- AI-generated natural-language summaries with evidence links.
- Confidence scores for each detected change.
- Support for batch comparison across many archive dates.
