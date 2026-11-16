"""Run the complete HTML comparison workflow.

Usage:
    python run_pipeline.py version1.html version2.html --output output
"""

from pathlib import Path
import argparse
import json
import shutil
import sys
import os

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from html_tree import build_tree, save_tree
from structural_match import structural_match
from structural_compare import create_structural_matches
from change_detector import detect_changes


def main():

    # ============================================================
    # ARGUMENTS
    # ============================================================

    p = argparse.ArgumentParser(
        description="Compare two HTML snapshots."
    )

    p.add_argument(
        "version1",
        type=Path
    )

    p.add_argument(
        "version2",
        type=Path
    )

    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output"
    )

    args = p.parse_args()


    # ============================================================
    # CHECK INPUT FILES
    # ============================================================

    for f in (args.version1, args.version2):

        if not f.exists():
            p.error(f"Input file not found: {f}")


    # ============================================================
    # CREATE OUTPUT DIRECTORY
    # ============================================================

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)


    # ============================================================
    # RUN PIPELINE INSIDE OUTPUT DIRECTORY
    # ============================================================

    old = Path.cwd()

    os.chdir(out)

    try:

        # --------------------------------------------------------
        # Copy input HTML files
        # --------------------------------------------------------

        shutil.copy2(
            args.version1,
            "version1.html"
        )

        shutil.copy2(
            args.version2,
            "version2.html"
        )


        # --------------------------------------------------------
        # Build HTML trees
        # --------------------------------------------------------

        t1 = build_tree("version1.html")
        t2 = build_tree("version2.html")

        if t1 is None or t2 is None:
            raise RuntimeError(
                "Could not build HTML tree."
            )


        # --------------------------------------------------------
        # Save complete trees
        # --------------------------------------------------------

        save_tree(
            t1,
            "tree_v1.json"
        )

        save_tree(
            t2,
            "tree_v2.json"
        )


        # --------------------------------------------------------
        # Structural matching
        # --------------------------------------------------------

        structural_match(
            t1,
            t2
        )

        create_structural_matches()


        # --------------------------------------------------------
        # Change detection
        # --------------------------------------------------------

        detect_changes()


        # ========================================================
        # LOAD GENERATED RESULTS
        # ========================================================

        changes = json.loads(
            Path("changes.json").read_text(
                encoding="utf-8"
            )
        )


        structural_matches = {}

        if Path("structural_matches.json").exists():

            structural_matches = json.loads(
                Path(
                    "structural_matches.json"
                ).read_text(
                    encoding="utf-8"
                )
            )


        tree_v1 = {}

        if Path("tree_v1.json").exists():

            tree_v1 = json.loads(
                Path("tree_v1.json").read_text(
                    encoding="utf-8"
                )
            )


        tree_v2 = {}

        if Path("tree_v2.json").exists():

            tree_v2 = json.loads(
                Path("tree_v2.json").read_text(
                    encoding="utf-8"
                )
            )


        # ========================================================
        # CREATE COMPLETE MASTER REPORT
        # ========================================================

        complete_report = {

            "inputs": {

                "version1": str(
                    args.version1.resolve()
                ),

                "version2": str(
                    args.version2.resolve()
                )

            },


            "node_counts": {

                "version1": len(
                    tree_v1
                ),

                "version2": len(
                    tree_v2
                )

            },


            "structural_matches": structural_matches,


            "changes": {

                "added": changes.get(
                    "added",
                    []
                ),

                "removed": changes.get(
                    "removed",
                    []
                ),

                "modified": changes.get(
                    "modified",
                    []
                ),

                "unchanged": changes.get(
                    "unchanged",
                    []
                )

            },


            "summary": {

                "added": len(
                    changes.get(
                        "added",
                        []
                    )
                ),

                "removed": len(
                    changes.get(
                        "removed",
                        []
                    )
                ),

                "modified": len(
                    changes.get(
                        "modified",
                        []
                    )
                ),

                "unchanged": len(
                    changes.get(
                        "unchanged",
                        []
                    )
                )

            }

        }


        # ========================================================
        # SAVE COMPLETE REPORT
        # ========================================================

        Path(
            "run_summary.json"
        ).write_text(

            json.dumps(
                complete_report,
                indent=4,
                ensure_ascii=False
            ),

            encoding="utf-8"
        )


        # ========================================================
        # FINISHED
        # ========================================================

        print()
        print("=" * 70)
        print("COMPLETE JSON REPORT CREATED")
        print("=" * 70)

        print()
        print(
            f"Result saved in: {out}"
        )

        print()
        print(
            "Master report:"
        )

        print(
            out / "run_summary.json"
        )

        print()
        print("=" * 70)


    finally:

        os.chdir(old)


if __name__ == "__main__":
    main()