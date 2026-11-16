import json
from difflib import SequenceMatcher


# ============================================================
# CONFIGURATION
# ============================================================

TREE_V1 = "tree_v1.json"
TREE_V2 = "tree_v2.json"
STRUCTURAL_MATCHES = "structural_matches.json"
OUTPUT_FILE = "changes.json"

# Minimum similarity required to consider two nodes a modification
MODIFICATION_THRESHOLD = 70


# ============================================================
# FILE LOADING
# ============================================================

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filename}")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {filename}")
        print(e)
        return None


# ============================================================
# TREE FLATTENING
# ============================================================

def flatten_tree(node, path="/html", result=None):
    """
    Converts nested HTML tree into a flat dictionary.

    Example:
        /html/body[0]/header[0]/h1[0]
    """

    if result is None:
        result = {}

    result[path] = {
        "tag": node.get("tag", ""),
        "text": normalize_text(node.get("text", "")),
        "attributes": node.get("attributes", {})
    }

    children = node.get("children", [])

    tag_counts = {}

    for child in children:
        tag = child.get("tag", "")

        index = tag_counts.get(tag, 0)
        tag_counts[tag] = index + 1

        child_path = f"{path}/{tag}[{index}]"

        flatten_tree(
            child,
            child_path,
            result
        )

    return result


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    return " ".join(str(text).split())


# ============================================================
# NODE CONTENT SIMILARITY
# ============================================================

def node_similarity(node1, node2):

    if node1 is None or node2 is None:
        return 0

    # Different HTML tags should not be treated as modifications
    if node1.get("tag") != node2.get("tag"):
        return 0

    text1 = normalize_text(node1.get("text", ""))
    text2 = normalize_text(node2.get("text", ""))

    attr1 = node1.get("attributes", {})
    attr2 = node2.get("attributes", {})

    # Compare text
    text_score = SequenceMatcher(
        None,
        text1,
        text2
    ).ratio() * 100

    # Compare attributes
    attr_score = SequenceMatcher(
        None,
        json.dumps(attr1, sort_keys=True),
        json.dumps(attr2, sort_keys=True)
    ).ratio() * 100

    # Empty structural nodes should NOT automatically become modified
    if not text1 and not text2:
        if attr1 == attr2:
            return 100
        else:
            return attr_score

    # Text is more important than attributes
    return round(
        (text_score * 0.85) +
        (attr_score * 0.15)
    )


# ============================================================
# LOAD STRUCTURAL MATCHES
# ============================================================

def load_structural_matches(filename):

    data = load_json(filename)

    if data is None:
        return {}

    matches = {}

    # --------------------------------------------------------
    # FORMAT 1
    #
    # {
    #   "matches": [
    #       {
    #           "v1_path": "...",
    #           "v2_path": "...",
    #           "score": 100
    #       }
    #   ]
    # }
    # --------------------------------------------------------

    if isinstance(data, dict):

        if "matches" in data and isinstance(data["matches"], list):

            for item in data["matches"]:

                v1 = (
                    item.get("v1_path")
                    or item.get("version1")
                    or item.get("path_v1")
                    or item.get("old_path")
                )

                v2 = (
                    item.get("v2_path")
                    or item.get("version2")
                    or item.get("path_v2")
                    or item.get("new_path")
                )

                if v1 and v2:
                    matches[v1] = v2

            return matches

        # ----------------------------------------------------
        # FORMAT 2
        #
        # {
        #   "/html": "/html",
        #   "/html/body[0]": "/html/body[0]"
        # }
        # ----------------------------------------------------

        for key, value in data.items():

            if isinstance(value, str):
                if key.startswith("/") and value.startswith("/"):
                    matches[key] = value

            elif isinstance(value, dict):

                v1 = (
                    value.get("v1_path")
                    or value.get("version1")
                    or value.get("path_v1")
                    or value.get("old_path")
                )

                v2 = (
                    value.get("v2_path")
                    or value.get("version2")
                    or value.get("path_v2")
                    or value.get("new_path")
                )

                if v1 and v2:
                    matches[v1] = v2

    # --------------------------------------------------------
    # FORMAT 3
    #
    # [
    #   {
    #       "v1_path": "...",
    #       "v2_path": "..."
    #   }
    # ]
    # --------------------------------------------------------

    elif isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            v1 = (
                item.get("v1_path")
                or item.get("version1")
                or item.get("path_v1")
                or item.get("old_path")
            )

            v2 = (
                item.get("v2_path")
                or item.get("version2")
                or item.get("path_v2")
                or item.get("new_path")
            )

            if v1 and v2:
                matches[v1] = v2

    return matches


# ============================================================
# FALLBACK STRUCTURAL MATCHING
# ============================================================

def fallback_match_nodes(tree1, tree2):

    matches = {}

    used_v2 = set()

    # First pass:
    # Match identical paths and identical tags
    for path1, node1 in tree1.items():

        if path1 in tree2:

            node2 = tree2[path1]

            if node1.get("tag") == node2.get("tag"):
                matches[path1] = path1
                used_v2.add(path1)

    # Second pass:
    # Match nodes with same tag and similar content
    for path1, node1 in tree1.items():

        if path1 in matches:
            continue

        best_path = None
        best_score = 0

        for path2, node2 in tree2.items():

            if path2 in used_v2:
                continue

            if node1.get("tag") != node2.get("tag"):
                continue

            score = node_similarity(node1, node2)

            if score > best_score:
                best_score = score
                best_path = path2

        if best_path and best_score >= MODIFICATION_THRESHOLD:

            matches[path1] = best_path
            used_v2.add(best_path)

    return matches


# ============================================================
# CHANGE DETECTION
# ============================================================

def detect_changes():

    print("=" * 70)
    print("LOADING FILES")
    print("=" * 70)

    tree1_raw = load_json(TREE_V1)
    tree2_raw = load_json(TREE_V2)

    if tree1_raw is None or tree2_raw is None:
        return

    structural_matches = load_structural_matches(
        STRUCTURAL_MATCHES
    )

    print(f"Loaded: {TREE_V1}")
    print(f"Loaded: {TREE_V2}")
    print(f"Loaded: {STRUCTURAL_MATCHES}")

    # --------------------------------------------------------
    # Flatten trees
    # --------------------------------------------------------

    tree1 = flatten_tree(tree1_raw)
    tree2 = flatten_tree(tree2_raw)

    print()
    print("=" * 70)
    print("NODE COUNTS")
    print("=" * 70)

    print(f"Version 1 nodes: {len(tree1)}")
    print(f"Version 2 nodes: {len(tree2)}")

    # --------------------------------------------------------
    # Structural matches
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("STRUCTURAL MATCHES LOADED")
    print("=" * 70)

    print(f"Matches found: {len(structural_matches)}")

    # --------------------------------------------------------
    # If structural matching file is empty,
    # use fallback matching.
    # --------------------------------------------------------

    if len(structural_matches) == 0:

        print()
        print("WARNING: No usable structural matches found.")
        print("Running fallback structural matching...")

        structural_matches = fallback_match_nodes(
            tree1,
            tree2
        )

        print(
            f"Fallback matches found: "
            f"{len(structural_matches)}"
        )

    # --------------------------------------------------------
    # Make sure matches are valid
    # --------------------------------------------------------

    valid_matches = {}

    for path1, path2 in structural_matches.items():

        if path1 not in tree1:
            continue

        if path2 not in tree2:
            continue

        valid_matches[path1] = path2

    structural_matches = valid_matches

    # --------------------------------------------------------
    # Change containers
    # --------------------------------------------------------

    added = []
    removed = []
    modified = []
    unchanged = []

    matched_v1 = set()
    matched_v2 = set()

    # --------------------------------------------------------
    # Analyze matched nodes
    # --------------------------------------------------------

    for path1, path2 in structural_matches.items():

        node1 = tree1[path1]
        node2 = tree2[path2]

        matched_v1.add(path1)
        matched_v2.add(path2)

        tag1 = node1.get("tag")
        tag2 = node2.get("tag")

        # Different tag = not a modification
        # Treat as structural replacement
        if tag1 != tag2:

            removed.append({
                "path": path1,
                "tag": tag1,
                "text": node1.get("text", "")
            })

            added.append({
                "path": path2,
                "tag": tag2,
                "text": node2.get("text", "")
            })

            continue

        text1 = normalize_text(
            node1.get("text", "")
        )

        text2 = normalize_text(
            node2.get("text", "")
        )

        attributes1 = node1.get(
            "attributes",
            {}
        )

        attributes2 = node2.get(
            "attributes",
            {}
        )

        # ----------------------------------------------------
        # Check whether content changed
        # ----------------------------------------------------

        if (
            text1 == text2
            and attributes1 == attributes2
        ):

            unchanged.append({
                "path_v1": path1,
                "path_v2": path2,
                "tag": tag1,
                "text": text1
            })

        else:

            similarity = node_similarity(
                node1,
                node2
            )

            modified.append({
                "path_v1": path1,
                "path_v2": path2,
                "tag": tag1,
                "old_text": text1,
                "new_text": text2,
                "old_attributes": attributes1,
                "new_attributes": attributes2,
                "similarity": round(similarity)
            })

    # --------------------------------------------------------
    # Find removed nodes
    # --------------------------------------------------------

    for path1, node1 in tree1.items():

        if path1 in matched_v1:
            continue

        removed.append({
            "path": path1,
            "tag": node1.get("tag", ""),
            "text": node1.get("text", "")
        })

    # --------------------------------------------------------
    # Find added nodes
    # --------------------------------------------------------

    for path2, node2 in tree2.items():

        if path2 in matched_v2:
            continue

        added.append({
            "path": path2,
            "tag": node2.get("tag", ""),
            "text": node2.get("text", "")
        })

    # --------------------------------------------------------
    # Sort results by path
    # --------------------------------------------------------

    added.sort(
        key=lambda x: x["path"]
    )

    removed.sort(
        key=lambda x: x["path"]
    )

    modified.sort(
        key=lambda x: x["path_v1"]
    )

    unchanged.sort(
        key=lambda x: x["path_v1"]
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    results = {
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(unchanged)
        },
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged
    }

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            indent=4,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # Print results
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("CHANGE DETECTION RESULTS")
    print("=" * 70)

    print()
    print(
        f"Added     : {len(added)}"
    )

    print(
        f"Removed   : {len(removed)}"
    )

    print(
        f"Modified  : {len(modified)}"
    )

    print(
        f"Unchanged : {len(unchanged)}"
    )

    # --------------------------------------------------------
    # Added
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("ADDED")
    print("-" * 70)

    if added:

        for item in added:

            print(
                f"+ {item['path']} "
                f"({item['tag']}) "
                f"{item['text']}"
            )

    else:
        print("None")

    # --------------------------------------------------------
    # Removed
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("REMOVED")
    print("-" * 70)

    if removed:

        for item in removed:

            print(
                f"- {item['path']} "
                f"({item['tag']}) "
                f"{item['text']}"
            )

    else:
        print("None")

    # --------------------------------------------------------
    # Modified
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("MODIFIED")
    print("-" * 70)

    if modified:

        for item in modified:

            print(
                f"~ {item['path_v1']}"
            )

            print(
                f"  OLD: {item['old_text']}"
            )

            print(
                f"  NEW: {item['new_text']}"
            )

            print(
                f"  Similarity: "
                f"{item['similarity']}"
            )

    else:
        print("None")

    # --------------------------------------------------------
    # Unchanged
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("UNCHANGED")
    print("-" * 70)

    if unchanged:

        for item in unchanged:

            print(
                f"= {item['path_v1']} "
                f"({item['tag']}) "
                f"{item['text']}"
            )

    else:
        print("None")

    print()
    print("=" * 70)
    print(
        f"Result saved to: {OUTPUT_FILE}"
    )
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    detect_changes()