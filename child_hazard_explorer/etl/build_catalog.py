"""Build catalog.json: the 17 SDG goals and 12 themes down to usable variables.

Scoped deliberately. The full graph under `undata/topic/Root` also carries every
agency corpus (WHO, ILO, UNESCO, ...) and runs to 33,000 nodes; walking all of
it takes ~20 minutes and trips the rate limit. The dashboard needs the goal and
theme trees, so that is what this walks.

Nothing is hand-constructed. A plausible-looking dcid (`undata/sdg_si_pov_dayt1`)
returns an empty 200, and the similar `sdg/...` namespace returns a *different
publisher's* numbers for the same indicator, so every identifier here is one the
graph handed us, checked by assert_un_scoped before it is written.

Usage:  python3 etl/build_catalog.py [--delay 0.1] [--out data/catalog.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from un_client import Rest, THEME_ROOT, TOPIC_ROOT, assert_un_scoped

GOAL_RE = re.compile(r"^undata/topic/sdgf/goal-(\d+)$")


class Walker:
    """Breadth-first walk with pacing, collecting edges and peer-group members."""

    def __init__(self, rest: Rest, delay: float, batch: int) -> None:
        self.rest = rest
        self.delay = delay
        self.batch = batch
        self.edges: dict[str, list[dict]] = {}
        self.meta: dict[str, dict] = {}
        self.calls = 0

    def _arc(self, nodes: list[str], prop: str) -> dict[str, list[dict]]:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.rest.arc(nodes, prop)

    def expand(self, roots: list[str]) -> None:
        seen = set(roots)
        layer = list(roots)
        while layer:
            nxt: list[str] = []
            for i in range(0, len(layer), self.batch):
                chunk = layer[i : i + self.batch]
                for parent, children in self._arc(chunk, "->relevantVariable").items():
                    self.edges[parent] = children
                    for child in children:
                        dcid = child.get("dcid", "")
                        self.meta[dcid] = {
                            "name": child.get("name", ""),
                            "types": child.get("types") or [],
                        }
                        if "Topic" in (child.get("types") or []) and dcid not in seen:
                            seen.add(dcid)
                            nxt.append(dcid)
            print(
                f"    depth done: {len(self.edges)} nodes, {self.calls} calls",
                file=sys.stderr,
            )
            layer = nxt

    def resolve_members(self) -> dict[str, list[dict]]:
        groups = sorted(
            {
                c["dcid"]
                for children in self.edges.values()
                for c in children
                if "StatVarPeerGroup" in (c.get("types") or [])
            }
        )
        print(f"  resolving {len(groups)} peer groups...", file=sys.stderr)
        members: dict[str, list[dict]] = {}
        for i in range(0, len(groups), self.batch):
            for group, nodes in self._arc(groups[i : i + self.batch], "->member").items():
                members[group] = [
                    n for n in nodes if "StatisticalVariable" in (n.get("types") or [])
                ]
        return members


def build_branch(dcid: str, walker: Walker, members: dict, seen: set[str] | None = None) -> dict:
    seen = seen if seen is not None else set()
    node = {
        "dcid": dcid,
        "name": walker.meta.get(dcid, {}).get("name", ""),
        "children": [],
        "variables": [],
    }
    if dcid in seen:
        return node
    seen = seen | {dcid}
    for child in walker.edges.get(dcid, []):
        cid = child["dcid"]
        types = child.get("types") or []
        if "Topic" in types:
            sub = build_branch(cid, walker, members, seen)
            if sub["children"] or sub["variables"]:
                node["children"].append(sub)
        elif "StatVarPeerGroup" in types:
            for var in members.get(cid, []):
                node["variables"].append(
                    {
                        "dcid": assert_un_scoped(var["dcid"], f"member of {cid}"),
                        "name": var.get("name", ""),
                    }
                )
        elif "StatisticalVariable" in types:
            node["variables"].append(
                {"dcid": assert_un_scoped(cid, f"child of {dcid}"), "name": child.get("name", "")}
            )
    return node


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--delay", type=float, default=0.1, help="seconds between calls")
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    out = Path(args.out) if args.out else root_dir / "data" / "catalog.json"

    rest = Rest()
    walker = Walker(rest, args.delay, args.batch)
    started = time.time()

    print("Finding goal and theme roots...", file=sys.stderr)
    top = walker._arc([TOPIC_ROOT, THEME_ROOT], "->relevantVariable")
    walker.edges.update(top)
    for parent, children in top.items():
        for child in children:
            walker.meta[child["dcid"]] = {
                "name": child.get("name", ""),
                "types": child.get("types") or [],
            }

    goal_ids = sorted(
        (c["dcid"] for c in top.get(TOPIC_ROOT, []) if GOAL_RE.match(c["dcid"])),
        key=lambda d: int(GOAL_RE.match(d).group(1)),
    )
    theme_ids = [c["dcid"] for c in top.get(THEME_ROOT, [])]
    print(f"  {len(goal_ids)} goals, {len(theme_ids)} themes", file=sys.stderr)

    print("Walking goal + theme subtrees...", file=sys.stderr)
    walker.expand(goal_ids + theme_ids)
    members = walker.resolve_members()

    goals = []
    for dcid in goal_ids:
        branch = build_branch(dcid, walker, members)
        branch["number"] = int(GOAL_RE.match(dcid).group(1))
        goals.append(branch)
    themes = sorted(
        (build_branch(d, walker, members) for d in theme_ids),
        key=lambda t: t["name"],
    )

    index: dict[str, dict] = {}

    def index_branch(branch: dict, goal: dict, trail: list[str]) -> None:
        here = trail + [branch["name"]] if branch["name"] else trail
        for var in branch["variables"]:
            index.setdefault(
                var["dcid"],
                {
                    "name": var["name"],
                    "goal": goal["number"],
                    "path": here,
                },
            )
        for sub in branch["children"]:
            index_branch(sub, goal, here)

    for goal in goals:
        index_branch(goal, goal, [])

    bad = [d for d in index if not d.startswith("undata/")]
    if bad:
        raise SystemExit(f"FATAL: {len(bad)} non-UN identifiers leaked: {bad[:5]}")

    catalog = {
        "source": "UN System Data Commons",
        "roots": {"goals": TOPIC_ROOT, "themes": THEME_ROOT},
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "goals": goals,
        "themes": themes,
        "variables": index,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(
        f"\ngoals={len(goals)} themes={len(themes)} variables={len(index)} "
        f"calls={walker.calls} elapsed={time.time() - started:.0f}s",
        file=sys.stderr,
    )
    print(f"written: {out} ({out.stat().st_size / 1024:.0f} KB)", file=sys.stderr)
    return 0 if len(goals) == 17 and index else 1


if __name__ == "__main__":
    raise SystemExit(main())
