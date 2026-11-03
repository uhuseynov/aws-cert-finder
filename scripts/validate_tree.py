#!/usr/bin/env python3
"""Validate the Cert Finder decision tree (data/tree.json).

Checks that every answer leads somewhere real, that every path ends in a
recommendation, that there are no loops, and that every certification has
the fields the frontend needs.

Usage:
    python scripts/validate_tree.py                 # validate, print a summary
    python scripts/validate_tree.py --paths         # also print every question path
    python scripts/validate_tree.py path/to/tree.json

Exit code 0 = OK (warnings allowed), 1 = errors found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_TREE = Path(__file__).resolve().parent.parent / "data" / "tree.json"

CERT_REQUIRED = ("name", "short_name", "level", "summary", "good_for", "status", "url")
CERT_LEVELS = {"Foundational", "Associate", "Professional", "Specialty", "Business"}
CERT_STATUSES = {"active", "beta"}
MIN_OPTIONS, MAX_OPTIONS = 2, 6
MAX_QUESTIONS_PER_PATH = 7


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_certs(certs: dict, rep: Report) -> None:
    if not isinstance(certs, dict) or not certs:
        rep.error("'certs' must be a non-empty object")
        return
    for cid, cert in certs.items():
        where = f"certs.{cid}"
        if not isinstance(cert, dict):
            rep.error(f"{where}: must be an object")
            continue
        for field in CERT_REQUIRED:
            value = cert.get(field)
            if not isinstance(value, str) or not value.strip():
                rep.error(f"{where}: missing or empty '{field}'")
        if cert.get("level") not in CERT_LEVELS:
            rep.error(f"{where}: level '{cert.get('level')}' not one of {sorted(CERT_LEVELS)}")
        if cert.get("status") not in CERT_STATUSES:
            rep.error(f"{where}: status '{cert.get('status')}' not one of {sorted(CERT_STATUSES)}")
        url = cert.get("url", "")
        if isinstance(url, str) and not url.startswith("https://"):
            rep.error(f"{where}: url must start with https://")
        price = cert.get("price_usd", "missing")
        if price == "missing":
            rep.error(f"{where}: 'price_usd' is required (use null if unknown)")
        elif price is not None and (not isinstance(price, int) or isinstance(price, bool) or price <= 0):
            rep.error(f"{where}: price_usd must be a positive integer or null")


def check_nodes(tree: dict, rep: Report) -> None:
    nodes = tree.get("nodes")
    certs = tree.get("certs") or {}
    if not isinstance(nodes, dict) or not nodes:
        rep.error("'nodes' must be a non-empty object")
        return

    for nid, node in nodes.items():
        where = f"nodes.{nid}"
        if not isinstance(node, dict):
            rep.error(f"{where}: must be an object")
            continue
        ntype = node.get("type")
        if ntype == "question":
            if not nid.startswith("q_"):
                rep.warn(f"{where}: question ids should start with 'q_'")
            if not str(node.get("text", "")).strip():
                rep.error(f"{where}: missing 'text'")
            options = node.get("options")
            if not isinstance(options, list):
                rep.error(f"{where}: 'options' must be a list")
                continue
            if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
                rep.error(f"{where}: needs {MIN_OPTIONS}-{MAX_OPTIONS} options, has {len(options)}")
            labels, targets = set(), set()
            for i, opt in enumerate(options):
                label = str(opt.get("label", "")).strip() if isinstance(opt, dict) else ""
                target = opt.get("next") if isinstance(opt, dict) else None
                if not label:
                    rep.error(f"{where}.options[{i}]: missing 'label'")
                if label in labels:
                    rep.error(f"{where}: duplicate option label '{label}'")
                labels.add(label)
                if target not in nodes:
                    rep.error(f"{where}.options[{i}]: 'next' points to unknown node '{target}'")
                elif target == nid:
                    rep.error(f"{where}.options[{i}]: points back to itself")
                if target in targets:
                    rep.warn(f"{where}: two options lead to the same node '{target}'")
                targets.add(target)
        elif ntype == "result":
            if not nid.startswith("r_"):
                rep.warn(f"{where}: result ids should start with 'r_'")
            primary = node.get("primary")
            if primary not in certs:
                rep.error(f"{where}: 'primary' cert '{primary}' not in certs")
            nxt = node.get("next_step")
            if nxt is not None:
                if nxt not in certs:
                    rep.error(f"{where}: 'next_step' cert '{nxt}' not in certs")
                if nxt == primary:
                    rep.error(f"{where}: next_step is the same as primary")
            if not str(node.get("reason", "")).strip():
                rep.error(f"{where}: missing 'reason'")
        else:
            rep.error(f"{where}: type must be 'question' or 'result', got '{ntype}'")


def walk_paths(tree: dict, rep: Report) -> list[list[tuple[str, str | None]]]:
    """Depth-first walk from start. Returns every path as [(node_id, chosen_label), ...]."""
    nodes = tree["nodes"]
    start = tree.get("start")
    if start not in nodes:
        rep.error(f"'start' points to unknown node '{start}'")
        return []
    if nodes[start].get("type") != "question":
        rep.error("'start' must be a question node")

    paths: list[list[tuple[str, str | None]]] = []

    def dfs(nid: str, trail: list[tuple[str, str | None]], on_stack: set[str]) -> None:
        node = nodes.get(nid)
        if not isinstance(node, dict):
            return
        if nid in on_stack:
            rep.error(f"loop detected: {' -> '.join(t[0] for t in trail)} -> {nid}")
            return
        if node.get("type") == "result":
            paths.append(trail + [(nid, None)])
            return
        for opt in node.get("options") or []:
            if isinstance(opt, dict) and opt.get("next") in nodes:
                dfs(opt["next"], trail + [(nid, opt.get("label"))], on_stack | {nid})

    dfs(start, [], set())
    return paths


def check_coverage(tree: dict, paths, rep: Report) -> None:
    nodes, certs = tree["nodes"], tree.get("certs") or {}
    reached = {nid for path in paths for nid, _ in path}
    for nid in nodes:
        if nid not in reached:
            rep.warn(f"node '{nid}' can't be reached from start")
    recommended = set()
    for path in paths:
        result = nodes[path[-1][0]]
        recommended.add(result.get("primary"))
        if result.get("next_step"):
            recommended.add(result["next_step"])
        questions = len(path) - 1
        if questions > MAX_QUESTIONS_PER_PATH:
            rep.warn(f"path to '{path[-1][0]}' asks {questions} questions (max {MAX_QUESTIONS_PER_PATH})")
    for cid in certs:
        if cid not in recommended:
            rep.warn(f"cert '{cid}' is never recommended")
    primaries = {nodes[p[-1][0]].get("primary") for p in paths}
    for cid in certs:
        if cid in recommended and cid not in primaries:
            rep.warn(f"cert '{cid}' only appears as a next step, never as the main pick")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tree", nargs="?", default=str(DEFAULT_TREE), help="path to tree.json")
    parser.add_argument("--paths", action="store_true", help="print every question path")
    args = parser.parse_args()

    rep = Report()
    try:
        tree = json.loads(Path(args.tree).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: can't read {args.tree}: {exc}")
        return 1

    for key in ("start", "nodes", "certs"):
        if key not in tree:
            rep.error(f"missing top-level key '{key}'")
    if rep.errors:
        for e in rep.errors:
            print(f"ERROR: {e}")
        return 1

    check_certs(tree["certs"], rep)
    check_nodes(tree, rep)
    paths = walk_paths(tree, rep) if not rep.errors else []
    if paths:
        check_coverage(tree, paths, rep)

    if args.paths and paths:
        nodes, certs = tree["nodes"], tree["certs"]
        print("Paths:")
        for path in paths:
            result = nodes[path[-1][0]]
            answers = " > ".join(label for _, label in path[:-1])
            pick = certs[result["primary"]]["short_name"]
            then = f"  (then {certs[result['next_step']]['short_name']})" if result.get("next_step") else ""
            print(f"  {answers}\n      => {pick}{then}")
        print()

    for w in rep.warnings:
        print(f"WARNING: {w}")
    for e in rep.errors:
        print(f"ERROR: {e}")

    if rep.errors:
        print(f"\nFAILED: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
        return 1

    questions = sum(1 for n in tree["nodes"].values() if n.get("type") == "question")
    results = len(tree["nodes"]) - questions
    longest = max(len(p) - 1 for p in paths)
    print(
        f"OK: {questions} questions, {results} results, {len(tree['certs'])} certs, "
        f"{len(paths)} paths, longest path {longest} questions"
        + (f", {len(rep.warnings)} warning(s)" if rep.warnings else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
