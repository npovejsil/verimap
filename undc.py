#!/usr/bin/env python3
"""
undc.py - a minimal, dependency-free client for the UN Data Commons MCP server.

The server speaks MCP over "streamable HTTP": you POST a JSON-RPC 2.0 request and
get back a text/event-stream whose `data:` line carries the JSON-RPC response.
It is stateless (no session header) and needs no authentication, so the whole
transport fits in one function.

Usage:
    python3 undc.py tools
    python3 undc.py playbook single
    python3 undc.py search "maternal mortality" --places Kenya Rwanda
    python3 undc.py meta --vars <dcid> --places <dcid>
    python3 undc.py obs --var <dcid> --place <dcid> --start 2010 --end 2023
    python3 undc.py child-obs --var <dcid> --parent africa --child-type Country
    python3 undc.py research "child mortality in Kenya"
    python3 undc.py raw search_indicators '{"query": "literacy rate"}'
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

SERVER = "https://unsd-datacommons.gcp.un-icc.cloud/mcp"

# The server's own instructions require reading a playbook before doing research.
PLAYBOOKS = {
    "single": "skill://data-commons-researcher/SKILL.md",
    "child": "skill://data-commons-child-places-researcher/SKILL.md",
    "multi": "skill://data-commons-multi-entity-researcher/SKILL.md",
}


class MCPError(RuntimeError):
    pass


class DataCommons:
    """One JSON-RPC call per method. No session to keep alive."""

    def __init__(self, url=SERVER, timeout=120):
        self.url = url
        self.timeout = timeout
        self._id = 0

    def rpc(self, method, params=None):
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params

        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                # Both types must be offered or the server rejects the request.
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode()
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raise MCPError(f"HTTP {e.code} from server: {e.read().decode()[:500]}") from e

        message = _parse_sse(body) if "text/event-stream" in ctype else json.loads(body)
        if "error" in message:
            raise MCPError(f"{method} failed: {message['error']}")
        return message.get("result", {})

    # --- discovery -------------------------------------------------------
    def handshake(self):
        return self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "undc.py", "version": "1.0"},
        })

    def list_tools(self):
        return self.rpc("tools/list").get("tools", [])

    def list_resources(self):
        return self.rpc("resources/list").get("resources", [])

    def read_resource(self, uri):
        contents = self.rpc("resources/read", {"uri": uri}).get("contents", [])
        return "\n".join(c.get("text", "") for c in contents)

    # --- tool calls ------------------------------------------------------
    def call(self, name, **arguments):
        """Call a tool and return its payload already decoded from JSON."""
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPError(f"tool {name} returned an error: {_text_of(result)}")
        text = _text_of(result)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    # Thin wrappers so the six tools are discoverable from Python.
    def search_indicators(self, query, places=None, per_search_limit=10, include_topics=True):
        return self.call("search_indicators", query=query, places=places,
                         per_search_limit=per_search_limit, include_topics=include_topics)

    def search_child_indicators(self, query, parent_place, sample_child_places,
                                per_search_limit=10, include_topics=True):
        return self.call("search_child_indicators", query=query, parent_place=parent_place,
                         sample_child_places=sample_child_places,
                         per_search_limit=per_search_limit, include_topics=include_topics)

    def get_variable_metadata(self, variable_dcids, entity_dcids):
        return self.call("get_variable_metadata",
                         variable_dcids=variable_dcids, entity_dcids=entity_dcids)

    def get_observations(self, variable_dcid, place_dcid, date="latest",
                         date_range_start=None, date_range_end=None, source_override=None):
        date = _date_mode(date, date_range_start, date_range_end)
        return self.call("get_observations", variable_dcid=variable_dcid, place_dcid=place_dcid,
                         date=date, date_range_start=date_range_start,
                         date_range_end=date_range_end, source_override=source_override)

    def get_child_observations(self, variable_dcid, parent_place_dcid, child_place_type,
                               date="latest", date_range_start=None, date_range_end=None,
                               source_override=None):
        date = _date_mode(date, date_range_start, date_range_end)
        if date == "all":
            raise MCPError('date="all" is not allowed for child observations; '
                           'use "latest" or a date range.')
        return self.call("get_child_observations", variable_dcid=variable_dcid,
                         parent_place_dcid=parent_place_dcid, child_place_type=child_place_type,
                         date=date, date_range_start=date_range_start,
                         date_range_end=date_range_end, source_override=source_override)

    def get_multi_entity_observations(self, variable_dcid, entities, date="latest", **kwargs):
        date = _date_mode(date, kwargs.get("date_range_start"), kwargs.get("date_range_end"))
        return self.call("get_multi_entity_observations", variable_dcid=variable_dcid,
                         entities=entities, date=date, **kwargs)


def _date_mode(date, start, end):
    """The server reads date_range_* only when date is the literal "range"."""
    if (start or end) and date in (None, "", "latest"):
        return "range"
    return date


def _parse_sse(body):
    """Pull the JSON-RPC message out of an SSE response."""
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise MCPError(f"no data frame in SSE response: {body[:300]}")


def _text_of(result):
    return "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")


def _dump(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj)


# --- the three-step research pipeline ------------------------------------
def research(dc, question, places=None, limit=5):
    """search_indicators -> get_variable_metadata -> get_observations.

    Never guess a DCID: every identifier used below comes out of a search result.
    """
    print(f"# Question: {question}\n")

    print("## 1. Searching for indicators")
    found = dc.search_indicators(question, places=places, per_search_limit=limit,
                                 include_topics=False)
    variables = _variables_from(found)
    if not variables:
        print("No statistical variables matched. Try broader wording.")
        return
    for v in variables[:limit]:
        print(f"  - {v['dcid']}\n      {v.get('name', '')}")

    top = variables[0]
    place_dcids = _places_from(found) or (places or [])
    if not place_dcids:
        print("\nNo place resolved; pass --places to scope the query.")
        return
    place = place_dcids[0]
    print(f"\n## 2. Metadata for {top['dcid']} at {place}")
    _dump(dc.get_variable_metadata([top["dcid"]], [place]))

    print(f"\n## 3. Observations")
    _dump(dc.get_observations(top["dcid"], place))


def _variables_from(payload):
    """Normalise a search response into [{dcid, name, places}].

    A search returns `variables` (concrete statistical variables) and, when
    include_topics is on, `topics` that group them under `memberVariables`.
    Human-readable names for every dcid live in a separate `dcidNameMappings`.
    """
    if not isinstance(payload, dict):
        return []
    names = payload.get("dcidNameMappings", {})
    out, seen = [], set()

    def add(dcid, places):
        if dcid and dcid not in seen:
            seen.add(dcid)
            out.append({"dcid": dcid, "name": names.get(dcid, ""), "places": places or []})

    for v in payload.get("variables", []):
        add(v.get("dcid"), v.get("placesWithData"))
    for t in payload.get("topics", []):
        for dcid in t.get("memberVariables", []):
            add(dcid, t.get("placesWithData"))
    return out


def _places_from(payload):
    """Places the server actually resolved, keyed by dcid."""
    if isinstance(payload, dict):
        return list(payload.get("dcidPlaceTypeMappings", {}))
    return []


def main():
    p = argparse.ArgumentParser(description="Minimal UN Data Commons MCP client.")
    p.add_argument("--server", default=SERVER)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tools", help="list the server's tools")
    sub.add_parser("resources", help="list the server's resources")

    pb = sub.add_parser("playbook", help="print a research playbook")
    pb.add_argument("which", choices=sorted(PLAYBOOKS), nargs="?", default="single")

    s = sub.add_parser("search", help="find statistical variables")
    s.add_argument("query")
    s.add_argument("--places", nargs="*")
    s.add_argument("--limit", type=int, default=10)

    cs = sub.add_parser("child-search", help="find indicators covering child places")
    cs.add_argument("query")
    cs.add_argument("--parent", required=True, help="human-readable name, e.g. 'Eastern Africa'")
    cs.add_argument("--samples", nargs="+", required=True,
                    help="5-6 sample child place names, e.g. Kenya Uganda Rwanda")
    cs.add_argument("--limit", type=int, default=10)

    m = sub.add_parser("meta", help="metadata and provenance for variables")
    m.add_argument("--vars", nargs="+", required=True)
    m.add_argument("--places", nargs="+", required=True)

    o = sub.add_parser("obs", help="time series for one variable at one place")
    o.add_argument("--var", required=True)
    o.add_argument("--place", required=True)
    o.add_argument("--date", default="latest")
    o.add_argument("--start")
    o.add_argument("--end")

    c = sub.add_parser("child-obs", help="one variable across child places")
    c.add_argument("--var", required=True)
    c.add_argument("--parent", required=True)
    c.add_argument("--child-type", required=True)
    c.add_argument("--date", default="latest")

    r = sub.add_parser("research", help="run the full discovery pipeline")
    r.add_argument("question")
    r.add_argument("--places", nargs="*")

    raw = sub.add_parser("raw", help="call any tool with JSON arguments")
    raw.add_argument("tool")
    raw.add_argument("arguments", nargs="?", default="{}")

    args = p.parse_args()
    dc = DataCommons(args.server)

    try:
        if args.cmd == "tools":
            for t in dc.list_tools():
                print(f"{t['name']}\n    {t['description'].strip().splitlines()[0][:150]}")
                print(f"    params: {', '.join(t['inputSchema'].get('properties', {}))}\n")
        elif args.cmd == "resources":
            for res in dc.list_resources():
                print(f"{res['uri']}\n    {res.get('description', '')[:150]}\n")
        elif args.cmd == "playbook":
            print(dc.read_resource(PLAYBOOKS[args.which]))
        elif args.cmd == "search":
            _dump(dc.search_indicators(args.query, places=args.places,
                                       per_search_limit=args.limit))
        elif args.cmd == "child-search":
            _dump(dc.search_child_indicators(args.query, args.parent, args.samples,
                                             per_search_limit=args.limit))
        elif args.cmd == "meta":
            _dump(dc.get_variable_metadata(args.vars, args.places))
        elif args.cmd == "obs":
            _dump(dc.get_observations(args.var, args.place, date=args.date,
                                      date_range_start=args.start, date_range_end=args.end))
        elif args.cmd == "child-obs":
            _dump(dc.get_child_observations(args.var, args.parent, args.child_type,
                                            date=args.date))
        elif args.cmd == "research":
            research(dc, args.question, places=args.places)
        elif args.cmd == "raw":
            _dump(dc.call(args.tool, **json.loads(args.arguments)))
    except MCPError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
