"""
Standalone demonstration of Milestone 2 NLP Semantic Analysis.

Demonstrates:
- Semantic similarity score & categorization
- Added and removed keywords (filtering stopwords)
- Added and removed named entities (e.g. DATE)
- Human-readable plain-English explanation
"""

import json
import sys
from pathlib import Path

# Ensure comparison-engine root is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.nlp.pipeline import analyze_text_modification, run_nlp_pipeline


def run_demo():
    print("=" * 70)
    print("  Milestone 2 NLP-Based Semantic Analysis - Standalone Demonstration")
    print("=" * 70)

    # Primary demonstration case: College examination announcement change
    old_text = "The college will conduct examinations in March."
    new_text = "The college has postponed examinations until April."

    print("\n--- Example 1: Examination Schedule Modification ---")
    print(f"Old Version: \"{old_text}\"")
    print(f"New Version: \"{new_text}\"")
    print("-" * 70)

    analysis = analyze_text_modification(old_text, new_text)

    score = analysis.get("similarity_score", 0.0)
    category = analysis.get("similarity_category", "unknown")
    method = analysis.get("similarity_method", "unknown")
    print(f"\n[Semantic Similarity]")
    print(f"  Score:    {score:.4f}")
    print(f"  Category: {category.upper()}")
    print(f"  Method:   {method}")

    print(f"\n[Keywords & Key Phrases]")
    print(f"  Added keywords:   {analysis.get('added_keywords', [])}")
    print(f"  Removed keywords: {analysis.get('removed_keywords', [])}")
    print(f"  Shared keywords:  {analysis.get('shared_keywords', [])}")

    print(f"\n[Named Entities]")
    print(f"  Added entities:   {analysis.get('added_entities', [])}")
    print(f"  Removed entities: {analysis.get('removed_entities', [])}")
    print(f"  Breakdown:        {analysis.get('entity_breakdown', {})}")

    print(f"\n[Human-Readable Explanation]")
    print(f"  {analysis.get('explanation', '')}")

    # Example 2: Pipeline integration with multiple changes
    print("\n" + "=" * 70)
    print("--- Example 2: Multi-Change Webpage Pipeline Integration ---")
    changes = [
        {
            "category": "modified",
            "element": "p",
            "oldValue": old_text,
            "newValue": new_text,
            "sourcePath": "/html/body/div/p[1]",
            "targetPath": "/html/body/div/p[1]",
        },
        {
            "category": "added",
            "element": "div",
            "oldValue": "",
            "newValue": "Important: All students must register before March 15th at the Academic Registrar office.",
            "sourcePath": "",
            "targetPath": "/html/body/div/div[2]",
        },
        {
            "category": "removed",
            "element": "span",
            "oldValue": "Late fee of $50 applies after February 28.",
            "newValue": "",
            "sourcePath": "/html/body/div/span[1]",
            "targetPath": "",
        },
    ]

    pipeline_result = run_nlp_pipeline(changes)
    overall = pipeline_result.get("overall", {})

    print(f"\n[Pipeline Summary Statistics]")
    print(f"  Modifications Analyzed:  {overall.get('total_modifications_analyzed', 0)}")
    print(f"  Additions Analyzed:      {overall.get('total_additions_analyzed', 0)}")
    print(f"  Removals Analyzed:       {overall.get('total_removals_analyzed', 0)}")
    print(f"  Avg Semantic Similarity: {overall.get('average_semantic_similarity', 0.0):.4f}")
    print(f"  Similarity Distribution: {overall.get('similarity_distribution', {})}")
    print(f"  Top Added Keywords:      {overall.get('top_added_keywords', [])[:8]}")
    print(f"  Top Removed Keywords:    {overall.get('top_removed_keywords', [])[:8]}")
    print(f"\n  Overall Summary: {overall.get('summary', '')}")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
