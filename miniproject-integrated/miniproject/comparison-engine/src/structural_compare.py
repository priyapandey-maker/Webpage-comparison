import json
from html_tree import build_tree


# ============================================================
# FLATTEN HTML TREE
# ============================================================

def flatten_tree(node, path="", index=0):

    nodes = []

    if path == "":
        current_path = f"/{node['tag']}"
    else:
        current_path = f"{path}/{node['tag']}[{index}]"

    nodes.append({
        "path": current_path,
        "node": node
    })

    for child_index, child in enumerate(
        node.get("children", [])
    ):

        nodes.extend(
            flatten_tree(
                child,
                current_path,
                child_index
            )
        )

    return nodes


# ============================================================
# TEXT SIMILARITY
# ============================================================

def text_similarity(text1, text2):

    text1 = (text1 or "").lower().strip()
    text2 = (text2 or "").lower().strip()

    if not text1 or not text2:
        return 0

    if text1 == text2:
        return 100

    words1 = set(text1.split())
    words2 = set(text2.split())

    if not words1 or not words2:
        return 0

    common = words1 & words2
    total = words1 | words2

    return round(
        len(common) / len(total) * 100
    )


# ============================================================
# STRUCTURAL SIMILARITY
# ============================================================

def structural_similarity(node1, node2):

    # Different HTML tags should not match
    if node1["tag"] != node2["tag"]:
        return 0

    score = 30

    # --------------------------------------------------------
    # ATTRIBUTES
    # --------------------------------------------------------

    attrs1 = set(
        node1.get("attributes", {}).keys()
    )

    attrs2 = set(
        node2.get("attributes", {}).keys()
    )

    if attrs1 == attrs2:
        score += 15

    elif attrs1 & attrs2:
        score += 7

    # --------------------------------------------------------
    # CHILD TAG STRUCTURE
    # --------------------------------------------------------

    children1 = [
        child["tag"]
        for child in node1.get("children", [])
    ]

    children2 = [
        child["tag"]
        for child in node2.get("children", [])
    ]

    if children1 == children2:
        score += 25

    elif set(children1) == set(children2):
        score += 15

    elif set(children1) & set(children2):
        score += 5

    # --------------------------------------------------------
    # CHILD COUNT
    # --------------------------------------------------------

    if len(children1) == len(children2):
        score += 10

    # --------------------------------------------------------
    # TEXT SIMILARITY
    # --------------------------------------------------------

    similarity = text_similarity(
        node1.get("text", ""),
        node2.get("text", "")
    )

    score += round(
        similarity * 0.20
    )

    return score


# ============================================================
# FIND BEST MATCH
# ============================================================

def find_best_match(
    node1,
    candidates,
    used_paths,
    threshold=60
):

    best_match = None
    best_score = 0

    for candidate in candidates:

        candidate_path = candidate["path"]

        # Do not match the same Version 2 node twice
        if candidate_path in used_paths:
            continue

        score = structural_similarity(
            node1["node"],
            candidate["node"]
        )

        if score > best_score:

            best_score = score
            best_match = candidate

    if best_match is None:
        return None, best_score

    if best_score < threshold:
        return None, best_score

    return best_match, best_score


# ============================================================
# BUILD STRUCTURAL MATCHES
# ============================================================

def create_structural_matches():

    print("\n")
    print("=" * 70)
    print("BUILDING STRUCTURAL MATCHES")
    print("=" * 70)

    # --------------------------------------------------------
    # BUILD TREES
    # --------------------------------------------------------

    print("\nLoading Version 1...")

    tree1 = build_tree(
        "version1.html"
    )

    print("Loading Version 2...")

    tree2 = build_tree(
        "version2.html"
    )

    if tree1 is None or tree2 is None:

        print(
            "ERROR: Could not build HTML trees."
        )

        return

    # --------------------------------------------------------
    # FLATTEN TREES
    # --------------------------------------------------------

    nodes1 = flatten_tree(tree1)
    nodes2 = flatten_tree(tree2)

    print("\nVersion 1 nodes:", len(nodes1))
    print("Version 2 nodes:", len(nodes2))

    # --------------------------------------------------------
    # STRUCTURAL MATCHING
    # --------------------------------------------------------

    matches = []

    used_paths = set()

    for node1 in nodes1:

        match, score = find_best_match(
            node1,
            nodes2,
            used_paths
        )

        if match:

            used_paths.add(
                match["path"]
            )

            matches.append({
                "version1_path": node1["path"],
                "version2_path": match["path"],
                "score": score
            })

            print(
                f"{node1['path']}"
                f"  -->  "
                f"{match['path']}"
                f"  | Score: {score}"
            )

    # --------------------------------------------------------
    # SAVE MATCHES
    # --------------------------------------------------------

    result = {
        "matches": matches
    }

    with open(
        "structural_matches.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STRUCTURAL MATCHING COMPLETE")
    print("=" * 70)

    print(
        "\nMatches found:",
        len(matches)
    )

    print(
        "\nSaved as: structural_matches.json"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    create_structural_matches()