"""The routes section of `Indexes`: the lateral graph and the walks over it
— `path`, and `route` with its traversability policies (RFC-003).
"""

from __future__ import annotations

from patternbuffer.codec import encode_value
from patternbuffer.model import ATTR_PREFIX, CANON


class RoutesMixin:
    """The routes section of `Indexes`."""

    def _lateral_edges(
        self, frame: str, valid_as_of: float | None, asserted_as_of: int | None,
    ) -> dict[str, set[str]]:
        """The as-of lateral graph as undirected adjacency over identity
        closures — the one structure `path()` and `route()` both search."""
        edges: dict[str, set[str]] = {}
        for row in self._buffer.visible(
            valid_as_of=valid_as_of, asserted_as_of=asserted_as_of, frame=frame,
            attribute_in=sorted(self._semantics.lateral_family()),
        ):
            if (row.value_type == "entity"
                    and not row.entity.startswith("a:")
                    and not row.entity.startswith(ATTR_PREFIX)):
                x, y = self._resolve(row.entity), self._resolve(row.value)
                edges.setdefault(x, set()).add(y)
                edges.setdefault(y, set()).add(x)
        return edges

    def path(
        self,
        a: str,
        b: str,
        frame: str = CANON,
        valid_as_of: float | None = None,
        asserted_as_of: int | None = None,
    ) -> list[str] | None:
        """BFS over the lateral graph (connects_to/adjacent_to, undirected).
        None = no path: vertical proximity is not connectivity.

        ``valid_as_of`` (PATH-TEMPORAL-V1): when given, edges are filtered to
        those valid at that time, so a severed edge (one whose ``valid_to`` has
        passed) drops from current routing while remaining visible to an earlier
        as-of query — `removed` is derived from temporal validity, never a
        stored flag. Default ``None`` = no bound (unchanged)."""
        a, b = self._resolve(a), self._resolve(b)
        edges = self._lateral_edges(frame, valid_as_of, asserted_as_of)
        if a == b:
            return [a]
        frontier = [[a]]
        visited = {a}
        while frontier:
            path_so_far = frontier.pop(0)
            for nxt in sorted(edges.get(path_so_far[-1], ())):
                if nxt in visited:
                    continue
                if nxt == b:
                    return path_so_far + [nxt]
                visited.add(nxt)
                frontier.append(path_so_far + [nxt])
        return None

    # ------------------------------------------- traversability (RFC-003)

    def _traversal_policy(self, kind: str) -> tuple[set, set] | None:
        """A declared traversal policy for a portal `kind` (RFC-003 §3), or None
        if the kind is not a gating portal. Host-declared as `traversal:<kind>`
        meta-assertions, scoped to the kind (a shut cabinet ≠ a shut door):
        `blocks_when_state` values and `blocks_when_relation` attrs. Presence of
        any declaration marks the kind as gating (so absence-of-state → obscured)."""
        rows = self._buffer.visible(entity=f"traversal:{kind}")
        states = {r.value for r in rows if r.attribute == "blocks_when_state"}
        rels = {r.value for r in rows if r.attribute == "blocks_when_relation"}
        if not states and not rels:
            return None  # unrelated traversal:<kind> metadata ≠ a gating policy
        return (states, rels)

    def _classify_portal(
        self, node: str, frame: str, valid_as_of: float | None, asserted_as_of: int | None
    ) -> tuple[str, dict | None]:
        """Derive a portal node's traversability status + evidence (RFC-003 §1/§4),
        never stored. clear (transparent / passable) | blocked (a declared
        blocking state or relation) | obscured (gating kind, state unestablished
        — the unknown doctrine, computed unknown_basis, never a fake row)."""
        kind_fold = self.fold_key(node, "kind", frame, valid_as_of, asserted_as_of)
        kind = kind_fold.winner.value if kind_fold.winner is not None else None
        policy = self._traversal_policy(kind) if isinstance(kind, str) else None
        if policy is None:
            return ("clear", None)  # not a gating portal kind — transparent
        blocking_states, blocking_rels = policy
        closure = sorted(self._closure_of(node))
        for attr in sorted(blocking_rels):
            for r in self._buffer.visible(
                entity_in=closure, attribute=attr, value_type="entity",
                frame=frame, valid_as_of=valid_as_of, asserted_as_of=asserted_as_of,
            ):
                obj = self._resolve(r.value) if isinstance(r.value, str) else r.value
                return ("blocked", {"evidence": [{
                    "entity": self._resolve(r.entity), "attribute": r.attribute,
                    "value": encode_value(obj), "assertion_id": r.id}]})
        state_fold = self.fold_key(node, "state", frame, valid_as_of, asserted_as_of)
        w = state_fold.winner
        if w is None:
            return ("obscured", {"unknown_basis": {
                "kind": "relational_absence", "portal": self._resolve(node),
                "required_attribute": "state", "frame": frame, "as_of": valid_as_of}})
        if w.value_type == "unresolved":
            return ("obscured", {"unknown_basis": {
                "kind": "unresolved_thunk", "portal": self._resolve(node),
                "required_attribute": "state", "assertion_id": w.id,
                "frame": frame, "as_of": valid_as_of}})
        if w.value in blocking_states:
            return ("blocked", {"evidence": [{
                "entity": self._resolve(node), "attribute": "state",
                "value": encode_value(w.value), "assertion_id": w.id}]})
        return ("clear", None)

    def route(
        self, a: str, b: str, frame: str = CANON,
        valid_as_of: float | None = None, asserted_as_of: int | None = None,
    ) -> dict:
        """Passability-aware routing (RFC-003): the structural `path()` graph,
        with each portal segment classified under the declared traversal policy.
        Two-pass (classify, never delete-then-BFS): a clear route if one exists,
        else the structural route with blocked/obscured segments flagged; only
        `no_path` when the as-of lateral graph has no route at all — so
        "all known ways are blocked" never collapses to "no path exists"."""
        a, b = self._resolve(a), self._resolve(b)
        if a == b:
            # routing to self: reflect the node's own status, never a forced
            # clear (Cx final review — a==b on a blocked portal is not clear).
            st, p = self._classify_portal(a, frame, valid_as_of, asserted_as_of)
            seg = {"node": a, "status": st}
            if p:
                seg.update(p)
            return {"route": [a], "status": st, "segments": [seg]}
        edges = self._lateral_edges(frame, valid_as_of, asserted_as_of)

        status_of: dict[str, str] = {}
        payload_of: dict[str, dict | None] = {}
        for node in edges:
            s, p = self._classify_portal(node, frame, valid_as_of, asserted_as_of)
            status_of[node] = s
            payload_of[node] = p

        def bfs(avoid_nonclear: bool) -> list[str] | None:
            if a == b:
                return [a]
            # a clear route requires clear endpoints too (Cx final review): a
            # non-clear source has no clear route, and a non-clear destination
            # is rejected by the same per-node check below before the b-return.
            if avoid_nonclear and status_of.get(a, "clear") != "clear":
                return None
            frontier, visited = [[a]], {a}
            while frontier:
                cur = frontier.pop(0)
                for nxt in sorted(edges.get(cur[-1], ())):
                    if nxt in visited:
                        continue
                    if avoid_nonclear and status_of.get(nxt, "clear") != "clear":
                        continue  # skip non-clear portals — including b itself
                    if nxt == b:
                        return cur + [nxt]
                    visited.add(nxt)
                    frontier.append(cur + [nxt])
            return None

        def result(route_nodes: list[str], overall: str) -> dict:
            segs = []
            for n in route_nodes:
                seg = {"node": n, "status": status_of.get(n, "clear")}
                if payload_of.get(n):
                    seg.update(payload_of[n])
                segs.append(seg)
            return {"route": route_nodes, "status": overall, "segments": segs}

        clear = bfs(avoid_nonclear=True)
        if clear is not None:
            return result(clear, "clear")
        structural = bfs(avoid_nonclear=False)
        if structural is None:
            return {"route": None, "status": "no_path", "segments": [],
                    "former_passages": self._former_passages(
                        a, b, frame, valid_as_of, asserted_as_of)}
        overall = "blocked" if any(status_of.get(n) == "blocked" for n in structural) else "obscured"
        return result(structural, overall)

    def _former_passages(
        self, a: str, b: str, frame: str,
        valid_as_of: float | None, asserted_as_of: int | None,
    ) -> list[dict]:
        """`removed` diagnostic (RFC-003 §4): lateral edges that **ended on or
        before** the query `valid_as_of` (`valid_to <= valid_as_of`) and touch a
        or b — former passages, history kept. Only meaningful under an explicit
        as-of (no `valid_as_of` → no "now" to be former relative to → []). Never
        a current segment; surfaced only to explain a missing connection."""
        if valid_as_of is None:
            return []
        endpoints = self._closure_of(a) | self._closure_of(b)
        out: list[dict] = []
        for row in self._buffer.visible(
            asserted_as_of=asserted_as_of, frame=frame,
            attribute_in=sorted(self._semantics.lateral_family()),
        ):
            if (row.value_type == "entity"
                    and isinstance(row.value, str)
                    and row.valid_to is not None
                    and row.valid_to <= valid_as_of
                    and (row.entity in endpoints or self._resolve(row.value) in endpoints)):
                out.append({
                    "entity": self._resolve(row.entity), "attribute": row.attribute,
                    "value": self._resolve(row.value), "valid_to": row.valid_to,
                    "assertion_id": row.id})
        return out
