import json
from difflib import SequenceMatcher
from html_tree import build_tree


# ============================================================
# CONFIGURATION
# ============================================================

# Minimum score required before two nodes can be considered
# possible structural matches.
MATCH_THRESHOLD = 55


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    return " ".join(str(text).lower().split())


# ============================================================
# ATTRIBUTE NORMALIZATION
# ============================================================

def normalize_attributes(attributes):
    """
    Convert attributes into a comparable representation.
    """

    if not attributes:
        return {}

    normalized = {}

    for key, value in attributes.items():

        if isinstance(value, list):
            normalized[key] = sorted(
                str(v).lower() for v in value
            )

        else:
            normalized[key] = str(value).lower()

    return normalized


# ============================================================
# TEXT SIMILARITY
# ============================================================

def text_similarity(text1, text2):

    text1 = normalize_text(text1)
    text2 = normalize_text(text2)

    if not text1 and not text2:
        return 1.0

    if not text1 or not text2:
        return 0.0

    return SequenceMatcher(
        None,
        text1,
        text2
    ).ratio()


# ============================================================
# ATTRIBUTE SIMILARITY
# ============================================================

def attribute_similarity(node1, node2):

    attr1 = normalize_attributes(
        node1.get("attributes", {})
    )

    attr2 = normalize_attributes(
        node2.get("attributes", {})
    )

    if not attr1 and not attr2:
        return 1.0

    if not attr1 or not attr2:
        return 0.0

    keys1 = set(attr1.keys())
    keys2 = set(attr2.keys())

    key_similarity = len(
        keys1.intersection(keys2)
    ) / len(
        keys1.union(keys2)
    )

    value_matches = 0
    total_common = 0

    for key in keys1.intersection(keys2):

        total_common += 1

        if attr1[key] == attr2[key]:
            value_matches += 1

    if total_common:
        value_similarity = (
            value_matches / total_common
        )
    else:
        value_similarity = 0

    return (
        key_similarity * 0.4
        +
        value_similarity * 0.6
    )


# ============================================================
# CHILD STRUCTURE SIMILARITY
# ============================================================

def child_structure_similarity(node1, node2):

    children1 = node1.get("children", [])
    children2 = node2.get("children", [])

    if not children1 and not children2:
        return 1.0

    if not children1 or not children2:
        return 0.0

    tags1 = [
        child.get("tag")
        for child in children1
    ]

    tags2 = [
        child.get("tag")
        for child in children2
    ]

    sequence_score = SequenceMatcher(
        None,
        tags1,
        tags2
    ).ratio()

    count_difference = abs(
        len(tags1) - len(tags2)
    )

    max_count = max(
        len(tags1),
        len(tags2)
    )

    if max_count == 0:
        count_score = 1.0
    else:
        count_score = 1 - (
            count_difference / max_count
        )

    return (
        sequence_score * 0.7
        +
        count_score * 0.3
    )


# ============================================================
# NODE TYPE SIMILARITY
# ============================================================

def tag_similarity(node1, node2):

    tag1 = node1.get("tag")
    tag2 = node2.get("tag")

    if tag1 == tag2:
        return 1.0

    # Similar semantic HTML elements
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    if tag1 in heading_tags and tag2 in heading_tags:
        return 0.7

    # These elements can sometimes represent similar
    # content depending on webpage structure.
    content_tags = {
        "p",
        "span",
        "div",
        "section",
        "article"
    }

    if tag1 in content_tags and tag2 in content_tags:
        return 0.45

    return 0.0


# ============================================================
# NODE SIMILARITY SCORE
# ============================================================

def calculate_node_score(node1, node2):

    tag_score = tag_similarity(
        node1,
        node2
    )

    if tag_score == 0:
        return 0

    text_score = text_similarity(
        node1.get("text", ""),
        node2.get("text", "")
    )

    attribute_score = attribute_similarity(
        node1,
        node2
    )

    child_score = child_structure_similarity(
        node1,
        node2
    )

    # Weighted score
    score = (
        tag_score * 0.35
        +
        text_score * 0.30
        +
        attribute_score * 0.15
        +
        child_score * 0.20
    )

    return round(score * 100)


# ============================================================
# CREATE NODE PATH
# ============================================================

def create_path(parent_path, node, index):

    tag = node.get("tag", "unknown")

    if parent_path:
        return f"{parent_path}/{tag}[{index}]"

    return f"/{tag}"


# ============================================================
# FLATTEN TREE
# ============================================================

def flatten_tree(node, parent_path="", index=0):

    path = create_path(
        parent_path,
        node,
        index
    )

    result = [{
        "node": node,
        "path": path,
        "parent_path": parent_path
    }]

    children = node.get("children", [])

    for child_index, child in enumerate(children):

        result.extend(
            flatten_tree(
                child,
                path,
                child_index
            )
        )

    return result


# ============================================================
# STRUCTURAL MATCHING
# ============================================================

def structural_match(tree1, tree2):

    nodes1 = flatten_tree(tree1)
    nodes2 = flatten_tree(tree2)

    matches = []

    used_version2 = set()

    # --------------------------------------------------------
    # Sort Version 1 nodes so that structurally important
    # nodes are matched first.
    # --------------------------------------------------------

    nodes1_sorted = sorted(
        nodes1,
        key=lambda item: (
            item["node"].get("tag") == "html",
            item["node"].get("tag") == "body",
            item["node"].get("tag") in {
                "header",
                "main",
                "section",
                "article",
                "footer"
            }
        ),
        reverse=True
    )

    for item1 in nodes1_sorted:

        node1 = item1["node"]

        best_match = None
        best_score = 0
        best_index = None

        for index2, item2 in enumerate(nodes2):

            if index2 in used_version2:
                continue

            node2 = item2["node"]

            score = calculate_node_score(
                node1,
                node2
            )

            # ------------------------------------------------
            # Parent relationship bonus
            # ------------------------------------------------

            parent_path1 = item1["parent_path"]
            parent_path2 = item2["parent_path"]

            if parent_path1 and parent_path2:

                parent_tags1 = parent_path1.split("/")
                parent_tags2 = parent_path2.split("/")

                if parent_tags1 and parent_tags2:

                    if parent_tags1[-1].split("[")[0] == \
                       parent_tags2[-1].split("[")[0]:

                        score += 10

            # ------------------------------------------------
            # Exact tag bonus
            # ------------------------------------------------

            if node1.get("tag") == node2.get("tag"):
                score += 10

            score = min(score, 100)

            if score > best_score:

                best_score = score
                best_match = item2
                best_index = index2

        # ----------------------------------------------------
        # Accept only sufficiently strong matches
        # ----------------------------------------------------

        if best_match and best_score >= MATCH_THRESHOLD:

            used_version2.add(best_index)

            matches.append({
                "version1_path": item1["path"],
                "version2_path": best_match["path"],
                "score": best_score,
                "version1_node": node1,
                "version2_node": best_match["node"]
            })

        else:

            matches.append({
                "version1_path": item1["path"],
                "version2_path": None,
                "score": 0,
                "version1_node": node1,
                "version2_node": None
            })

    # --------------------------------------------------------
    # Find Version 2 nodes that were never matched.
    # --------------------------------------------------------

    matched_v2_paths = {
        match["version2_path"]
        for match in matches
        if match["version2_path"] is not None
    }

    unmatched_v2 = []

    for item2 in nodes2:

        if item2["path"] not in matched_v2_paths:

            unmatched_v2.append({
                "version2_path": item2["path"],
                "version2_node": item2["node"]
            })

    return matches, unmatched_v2


# ============================================================
# PRINT RESULTS
# ============================================================

def print_results(matches, unmatched_v2):

    print("\n")
    print("=" * 70)
    print("STRUCTURAL MATCHING RESULTS")
    print("=" * 70)

    for match in matches:

        v1_path = match["version1_path"]
        v2_path = match["version2_path"]
        score = match["score"]

        if v2_path:

            print(
                f"{v1_path}"
                f"  -->  "
                f"{v2_path}"
                f"  | Score: {score}"
            )

        else:

            print(
                f"{v1_path}"
                f"  -->  NO MATCH"
                f"  | Score: 0"
            )

    print("\n")
    print("=" * 70)
    print("UNMATCHED VERSION 2 NODES")
    print("=" * 70)

    for item in unmatched_v2:

        print(
            f"{item['version2_path']}"
            f"  | NEW NODE"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("\nLoading Version 1...")

    tree1 = build_tree(
        "version1.html"
    )

    print("Loading Version 2...")

    tree2 = build_tree(
        "version2.html"
    )

    if tree1 is None:
        print("ERROR: Could not build Version 1 tree.")
        exit()

    if tree2 is None:
        print("ERROR: Could not build Version 2 tree.")
        exit()

    # --------------------------------------------------------
    # Count nodes
    # --------------------------------------------------------

    nodes1 = flatten_tree(tree1)
    nodes2 = flatten_tree(tree2)

    print("\n")
    print("=" * 70)
    print("NODE COUNTS")
    print("=" * 70)

    print(
        f"Version 1 nodes: {len(nodes1)}"
    )

    print(
        f"Version 2 nodes: {len(nodes2)}"
    )

    # --------------------------------------------------------
    # Perform matching
    # --------------------------------------------------------

    matches, unmatched_v2 = structural_match(
        tree1,
        tree2
    )

    # --------------------------------------------------------
    # Print results
    # --------------------------------------------------------

    print_results(
        matches,
        unmatched_v2
    )

    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------

    output = {
        "version1_node_count": len(nodes1),
        "version2_node_count": len(nodes2),
        "matches": matches,
        "unmatched_version2": unmatched_v2
    }

    with open(
        "structural_matches.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n")
    print("=" * 70)
    print("RESULT SAVED")
    print("=" * 70)

    print(
        "structural_matches.json"
    )