from bs4 import BeautifulSoup
import re
import json


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# READ HTML
# ============================================================

def load_html(filename):

    with open(filename, "r", encoding="utf-8") as file:
        html = file.read()

    return BeautifulSoup(html, "html.parser")


# ============================================================
# CREATE FINGERPRINT
# ============================================================

def create_fingerprint(node):

    return {
        "tag": node["tag"],

        "attributes": sorted(
            node["attributes"].keys()
        ),

        "children_tags": [
            child["tag"]
            for child in node["children"]
        ],

        "child_count": len(
            node["children"]
        )
    }


# ============================================================
# CREATE GENERIC NODE
# ============================================================

def create_node(tag):

    node = {
        "tag": tag.name,
        "text": "",
        "attributes": {},
        "children": []
    }

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    direct_text = tag.find(
        string=True,
        recursive=False
    )

    if direct_text:

        node["text"] = clean_text(
            direct_text
        )

    # --------------------------------------------------------
    # ATTRIBUTES
    # --------------------------------------------------------

    for key, value in tag.attrs.items():

        if isinstance(value, list):

            node["attributes"][key] = value

        else:

            node["attributes"][key] = value

    # --------------------------------------------------------
    # CHILDREN
    # --------------------------------------------------------

    for child in tag.find_all(
        recursive=False
    ):

        # Ignore scripts/styles
        if child.name in [
            "script",
            "style",
            "noscript"
        ]:
            continue

        child_node = create_node(child)

        # Add fingerprint
        child_node["fingerprint"] = (
            create_fingerprint(child_node)
        )

        node["children"].append(
            child_node
        )

    return node


# ============================================================
# BUILD HTML TREE
# ============================================================

def build_tree(filename):

    soup = load_html(filename)

    html_tag = soup.find("html")

    if not html_tag:
        return None

    root = create_node(html_tag)

    # Add root fingerprint
    root["fingerprint"] = (
        create_fingerprint(root)
    )

    return root


# ============================================================
# SAVE TREE
# ============================================================

def save_tree(tree, filename):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            tree,
            file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 70)
    print("BUILDING HTML TREES")
    print("=" * 70)

    # --------------------------------------------------------
    # VERSION 1
    # --------------------------------------------------------

    print("\nLoading Version 1...")

    tree1 = build_tree(
        "version1.html"
    )

    if tree1 is None:

        print(
            "ERROR: Could not find <html> in version1.html"
        )

        exit()

    save_tree(
        tree1,
        "tree_v1.json"
    )

    print(
        "Version 1 tree saved as: tree_v1.json"
    )

    # --------------------------------------------------------
    # VERSION 2
    # --------------------------------------------------------

    print("\nLoading Version 2...")

    tree2 = build_tree(
        "version2.html"
    )

    if tree2 is None:

        print(
            "ERROR: Could not find <html> in version2.html"
        )

        exit()

    save_tree(
        tree2,
        "tree_v2.json"
    )

    print(
        "Version 2 tree saved as: tree_v2.json"
    )

    # --------------------------------------------------------
    # DISPLAY VERSION 1 TREE
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("HTML TREE WITH FINGERPRINTS - VERSION 1")
    print("=" * 70)

    print(
        json.dumps(
            tree1,
            indent=4,
            ensure_ascii=False
        )
    )

    # --------------------------------------------------------
    # NODE COUNT
    # --------------------------------------------------------

    def count_nodes(node):

        count = 1

        for child in node.get(
            "children",
            []
        ):

            count += count_nodes(child)

        return count

    count1 = count_nodes(tree1)
    count2 = count_nodes(tree2)

    print("\n")
    print("=" * 70)
    print("NODE COUNTS")
    print("=" * 70)

    print(
        f"Version 1 nodes: {count1}"
    )

    print(
        f"Version 2 nodes: {count2}"
    )

    print("\n")
    print("=" * 70)
    print("TREE FILES CREATED SUCCESSFULLY")
    print("=" * 70)

    print("\nCreated:")
    print("  tree_v1.json")
    print("  tree_v2.json")

    print("\nYou can now run:")
    print("  python structural_compare.py")
    print("  python change_detector.py")

    