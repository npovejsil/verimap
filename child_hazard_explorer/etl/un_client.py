"""Clients for the UN System Data Commons graph.

Two ways in, and the distinction matters:

* REST (`Rest`) walks the graph's structure. The deployment is federated with the
  wider Data Commons graph, so the same endpoints happily answer for other
  publishers without saying so. `sdg/SI_POV_DAY1` and `undata/sdg/SI_POV_DAY1`
  both return HTTP 200 for Kenya 2021 -- 36.0 and 46.4 respectively. Only the
  second is UN-governed. Everything here therefore starts from a UN root node
  and is checked by `assert_un_scoped`.
* MCP (`Mcp`) is the documented way to *discover* variables. REST must never be
  used to search for indicators.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Iterator

sys.stdout.reconfigure(encoding="utf-8")

REST_BASE = "https://unsd-datacommons.gcp.un-icc.cloud/core/api/v2"
MCP_URL = "https://unsd-datacommons.gcp.un-icc.cloud/mcp"
USER_AGENT = "un-dashboard-etl/0.1"

# The two documented UN roots. Anything reached by walking from here is in corpus.
TOPIC_ROOT = "undata/topic/Root"
THEME_ROOT = "undata/topic/theme/Root"

# A /node request accepts at most 17 `country/` entities. The 18th makes the
# whole request fail with 403 -- which reads like an auth or rate-limit problem
# and is neither. Measured, not documented: 17 countries pass and 18 fail with
# any property; 18 topics or 18 continents are fine; and 17 countries plus 5
# topics (22 nodes total) is fine, so the cap counts `country/` nodes only,
# not total nodes and not URL length (16 countries padded to 899 chars passes).
MAX_COUNTRY_NODES = 17

# Places are shared reference nodes, so they are legitimately un-prefixed.
_PLACE_PREFIXES = ("country/", "undata-geo/", "Earth")
_CONTINENTS = ("africa", "asia", "europe", "northamerica", "southamerica", "oceania")


class CorpusError(RuntimeError):
    """Raised when an identifier falls outside the UN-governed corpus."""


def is_un_scoped(dcid: str) -> bool:
    return dcid.startswith("undata/")


def is_place(dcid: str) -> bool:
    return dcid in _CONTINENTS or dcid.startswith(_PLACE_PREFIXES)


def assert_un_scoped(dcid: str, context: str = "") -> str:
    """Guard every statistical identifier before it reaches an output file.

    Cheap to call and the whole reason the catalog can be trusted.
    """
    if not is_un_scoped(dcid):
        where = f" ({context})" if context else ""
        raise CorpusError(
            f"{dcid!r} is outside the UN corpus{where}. "
            "Only undata/ identifiers reached from a UN root may be used."
        )
    return dcid


class Rest:
    """Structural graph navigation. Not for discovery, not for search."""

    def __init__(self, base: str = REST_BASE, timeout: int = 120) -> None:
        self.base = base
        self.timeout = timeout

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        """GET with backoff for genuine transients.

        Note that the most common 403 here is NOT throttling: it is the
        `country/` node cap described on `MAX_COUNTRY_NODES`, which no amount
        of retrying will clear. `node()` splits those requests before they are
        sent, so anything still failing here is worth retrying.
        """
        # The arrows and braces in a property must reach the server encoded.
        url = f"{self.base}/{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        delay = 2.0
        for attempt in range(8):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                if err.code not in (403, 429, 500, 502, 503, 504) or attempt == 7:
                    raise
            except urllib.error.URLError:
                if attempt == 7:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
        raise RuntimeError("unreachable")

    def node(self, dcids: Iterable[str], prop: str) -> dict[str, Any]:
        """Follow `prop` from each dcid, following pagination to completion.

        Pagination here is a trap worth spelling out. The response paginates
        across the *whole batch*, and a node whose arcs did not fit on the
        current page comes back present but with an empty ``arcs`` object --
        it is not omitted, and nothing signals the truncation except a
        top-level ``nextToken``. Asking for 40 topics returns all 40 keys with
        26 of them silently empty. Ignoring the token therefore yields a
        catalog that looks structurally correct and is mostly hollow.
        """
        dcids = list(dcids)
        if not dcids:
            return {}

        countries = [d for d in dcids if d.startswith("country/")]
        if len(countries) > MAX_COUNTRY_NODES:
            # Split on the country axis and merge; other node types ride along
            # with the first chunk so they are fetched exactly once.
            others = [d for d in dcids if not d.startswith("country/")]
            out: dict[str, Any] = {}
            for i in range(0, len(countries), MAX_COUNTRY_NODES):
                chunk = countries[i : i + MAX_COUNTRY_NODES] + (others if i == 0 else [])
                out.update(self.node(chunk, prop))
            return out

        merged: dict[str, Any] = {}
        seen: dict[tuple[str, str], set[str]] = {}
        token: str | None = None
        while True:
            params = [("nodes", d) for d in dcids] + [("property", prop)]
            if token:
                params.append(("nextToken", token))
            response = self._get("node", params)
            for key, value in response.get("data", {}).items():
                target = merged.setdefault(key, {"arcs": {}})["arcs"]
                for name, payload in (value.get("arcs") or {}).items():
                    bucket = target.setdefault(name, {"nodes": []})["nodes"]
                    known = seen.setdefault((key, name), set())
                    for item in payload.get("nodes", []):
                        dcid = item.get("dcid") or item.get("value", "")
                        if dcid not in known:
                            known.add(dcid)
                            bucket.append(item)
            token = response.get("nextToken")
            if not token:
                return merged

    def arc(self, dcids: Iterable[str], prop: str) -> dict[str, list[dict[str, Any]]]:
        """Like `node`, flattened to {dcid: [linked nodes]}."""
        # "<-containedInPlace{typeOf:Country}" comes back keyed as
        # "containedInPlace": strip both the direction arrows and the qualifier.
        name = prop.lstrip("<->").split("{")[0]
        data = self.node(dcids, prop)
        return {
            key: value.get("arcs", {}).get(name, {}).get("nodes", [])
            for key, value in data.items()
        }

    def observations(
        self,
        variable: str,
        entity_expression: str | None = None,
        entities: Iterable[str] | None = None,
        date: str = "LATEST",
    ) -> dict[str, Any]:
        """Fetch observations for one UN variable.

        Either an entity expression (e.g. ``Earth<-containedInPlace+{typeOf:Country}``)
        or an explicit list of entity dcids. All ~170 countries come back in one
        call in roughly a third of a second.
        """
        assert_un_scoped(variable, "observation request")
        params = [("date", date), ("variable.dcids", variable)]
        if entity_expression:
            params.append(("entity.expression", entity_expression))
        for entity in entities or []:
            params.append(("entity.dcids", entity))
        params += [("select", s) for s in ("date", "value", "variable", "entity")]
        return self._get("observation", params)


class Mcp:
    """Minimal JSON-RPC client for the MCP server (streamable HTTP)."""

    def __init__(self, url: str = MCP_URL, timeout: int = 120) -> None:
        self.url = url
        self.timeout = timeout
        self._id = 0
        self._ready = False

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        # Streamable HTTP may answer as plain JSON or as server-sent events.
        if raw.lstrip().startswith("{"):
            return json.loads(raw)["result"]
        payloads = [line[5:] for line in raw.splitlines() if line.startswith("data:")]
        return json.loads(payloads[-1])["result"]

    def _handshake(self) -> None:
        if self._ready:
            return
        self._call(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "un-dashboard-etl", "version": "0.1"},
            },
        )
        self._ready = True

    def tools(self) -> list[dict[str, Any]]:
        self._handshake()
        return self._call("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._handshake()
        return self._call("tools/call", {"name": name, "arguments": arguments})


def walk(rest: Rest, roots: list[str], prop: str = "->relevantVariable", batch: int = 40) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Breadth-first walk of the topic tree, yielding (parent, children).

    Follows Topic nodes only; other node types are yielded but not expanded, so
    peer groups and statvars terminate the walk. The full tree is ~29 requests.
    """
    seen: set[str] = set(roots)
    layer = list(roots)
    while layer:
        nxt: list[str] = []
        for i in range(0, len(layer), batch):
            chunk = layer[i : i + batch]
            for parent, children in rest.arc(chunk, prop).items():
                yield parent, children
                for child in children:
                    dcid = child.get("dcid", "")
                    if "Topic" in (child.get("types") or []) and dcid not in seen:
                        seen.add(dcid)
                        nxt.append(dcid)
        layer = nxt
