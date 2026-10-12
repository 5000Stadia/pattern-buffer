"""The world service (WORLD-SERVICE-V1): one host per world, every module a client.

A library class that sits OUTSIDE the engine core (the engine never imports
this module): a host that opened a `World` attaches it, and other modules read
through the player's view, never raw canon.

- `attach(world)` binds the service to a World the host opened, on the host's
  thread. Every job that needs the World runs inside `pump()`, which the host
  calls from that same thread, so the one-handle, one-thread rules hold by
  construction.
- Viewer reads never touch the World. They run on a reader thread against an
  in-memory `World.snapshot()` refreshed by `pump()` only when the committed
  log head or the classifier's `verdict_version` moved.
- A viewer's `resolve` is an owner job: it plants, forces (or serves the memo)
  and mirrors what the player perceives into the view frame in ONE unit.
- `record` exists on the standalone runner only (a world with no author).

`python -m patternbuffer.service` is that runner (localhost HTTP + JSON,
standard library only).
"""

from __future__ import annotations

import argparse
import collections
import importlib
import inspect
import json
import logging
import queue
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from patternbuffer import AtomicAbort, World
from patternbuffer.mcp import FORCED_PARAMS, V1_READS, dispatch
from patternbuffer.model import (
    ATTR_PREFIX,
    CANON,
    CANON_IDENTITY_EDGES,
    ID_RE,
    MECHANISM_ATTRIBUTES,
    META_ATTRIBUTES,
    POLICIES,
    SEMANTICS_PREDICATES,
    TASK_RESOLVE,
)
from patternbuffer.porcelain import Porcelain

logger = logging.getLogger(__name__)

# ------------------------------------------------------------ the allowlist
# Explicit, never reflected (WORLD-SERVICE-V1 §3). A porcelain verb added later
# is excluded until it is classified here; the walk test enforces it.

VIEWER_READS = (
    "snapshot", "state", "state_union", "where", "aggregate", "confidence",
    "locate", "contents", "composition", "features", "path", "route",
    "neighborhood", "salience", "events", "in_transit", "entities",
    "facts", "refer", "canonical_attribute",
)

_CROSS_FRAME = "reads across frames or reports canon or global identity state"
VIEWER_EXCLUDED: dict[str, str] = {
    # reads that cross frames, or report canon / global identity state
    "frame_diff": "takes two arbitrary frames",
    "who_knows": "reports every knows:* frame",
    "proposals": "a canon identity diagnostic",
    "identity_conflicts": "a canon identity diagnostic",
    "typing_conflicts": "a canon identity diagnostic",
    "correlations": "a canon identity diagnostic",
    "correlation_conflicts": "a canon identity diagnostic",
    "fidelity_audit": "a diagnostic over a whole frame (canon by default)",
    "axis_heads": "reports global log positions; a viewer gets `now` instead",
    # the service's own verbs
    "resolve": "served by the service (pinned frame and perception)",
    # writes and model-backed verbs: a viewer writes nothing, calls no model
    "ingest_structured": "a write", "commit_set": "a write", "retract": "a write",
    "reconcile": "a write", "adjudicate_deferred": "a write", "confirm": "a write",
    "merge": "a write", "reject": "a write", "correlate": "a write",
    "retype": "a write", "begin_build": "a write", "seal_build": "a write",
    "abort_build": "a write", "build": "a write", "continue_frame": "a write",
    "extract": "reaches the model", "ingest": "a write that reaches the model",
    "ask": "reaches the model",
}

# What a viewer's reads force, beyond MCP's FORCED_PARAMS (refer's model/learn).
_VIEWER_FORCED: dict[tuple[str, str], Any] = {
    **{k: v for k, v in FORCED_PARAMS.items() if k[0] in VIEWER_READS},
    ("facts", "include_meta"): False,
}

# Arguments no viewer may name on any verb. `frame_scope` (FRAME-CONTINUITY-V1
# §5) is the host's, set at `attach`: a viewer cannot widen its own view.
_REFUSED_ARGS = ("frame", "frame_scope")

DEFAULT_WAIT = 2.0
DEFAULT_RETRY_AFTER = 1.0

# A `record` item may carry exactly these keys. The service sets the frame and
# the status itself; every other key would let a caller reach beyond a play
# event (aliases, a declaration hint, a source, a correction ...).
_RECORD_KEYS = frozenset({"entity", "attribute", "value", "value_type",
                          "valid_from", "valid_to", "timeless"})
_RECORD_VALUE_TYPES = frozenset({"entity", "literal", "delta"})
_RECORD_BARRED_ATTRIBUTES = (MECHANISM_ATTRIBUTES | SEMANTICS_PREDICATES
                             | CANON_IDENTITY_EDGES | META_ATTRIBUTES)


class Refused(ValueError):
    """The call asks for something the caller's role does not have (a frame it
    may not name, a verb outside its allowlist, a write key it may not carry).
    Nothing was done."""


class NoModel(RuntimeError):
    """The model route has no model in this process (the standalone runner
    started without a generator for this call)."""


class _CapExceeded(BaseException):
    """Raised from inside the gated model callable when the rate cap is spent.
    A BaseException so the engine's own `except Exception` fallbacks (the
    classifier's) cannot swallow it; the unit rolls back and the job turns it
    into `deferred`."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("model rate cap exhausted")
        self.retry_after = retry_after


class RateCap:
    """A sliding-window cap on model calls: at most ``max_calls`` per
    ``per_seconds``. The service counts only calls the host's `model_route`
    sends to the model, and only for viewer-initiated resolve jobs."""

    def __init__(self, max_calls: int, per_seconds: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if max_calls < 0 or per_seconds <= 0:
            raise ValueError("RateCap needs max_calls >= 0 and per_seconds > 0")
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._clock = clock
        self._stamps: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def _trim(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= self.per_seconds:
            self._stamps.popleft()

    def try_acquire(self) -> bool:
        """Spend one call from the window; False (and nothing spent) when full."""
        with self._lock:
            now = self._clock()
            self._trim(now)
            if len(self._stamps) >= self.max_calls:
                return False
            self._stamps.append(now)
            return True

    def retry_after(self) -> float:
        """Seconds until a call would be admitted."""
        with self._lock:
            now = self._clock()
            self._trim(now)
            if len(self._stamps) < self.max_calls or not self._stamps:
                return 0.0 if self.max_calls else self.per_seconds
            return max(0.0, self._stamps[0] + self.per_seconds - now)


# ------------------------------------------------------------------ jobs


class _Job:
    """One owner job (a viewer resolve or a record), run inside `pump()`."""

    def __init__(self, kind: str, args: dict[str, Any]) -> None:
        self.kind = kind
        self.args = args
        self.state = "queued"        # queued -> running -> done | cancelled
        self.result: Any = None
        self.error: BaseException | None = None
        self.lock = threading.Lock()
        self.done = threading.Event()


class _Read:
    """One viewer read, run on the reader thread."""

    def __init__(self, verb: str, args: dict[str, Any]) -> None:
        self.verb = verb
        self.args = args
        self.result: Any = None
        self.error: BaseException | None = None
        self.done = threading.Event()


def _detached() -> dict:
    return {"status": "detached"}


# --------------------------------------------------------------- the service


class WorldService:
    """One host per world; every other module a client (WORLD-SERVICE-V1).

    ``model_route(schema) -> "code" | "model"`` is the host's routing, read
    only to decide which model calls the ``rate`` cap counts. ``standalone``
    marks the runner (no author): only there may a session be a recorder.
    """

    def __init__(self, model_route: Callable[[dict], str] | None = None,
                 rate: RateCap | None = None, *, standalone: bool = False,
                 retry_after: float = DEFAULT_RETRY_AFTER,
                 read_timeout: float = 30.0) -> None:
        self._model_route = model_route
        self._rate = rate
        # r5: the cap is applied by the gated callable the host injected into
        # its World, only while a viewer job runs on the owner thread
        self._job = threading.local()
        self._gated = False
        self._standalone = standalone
        self._retry_after = retry_after
        self._read_timeout = read_timeout
        # attached state
        self._world: World | None = None
        self._owner: int | None = None
        self._view_frame: str | None = None
        self._frame_scope = "exact"
        self._perceptible: Callable[[World, str, str], bool] | None = None
        self._now: float | None = None
        self._valid_head: float | None = None
        self._key: tuple[int, int] | None = None
        self.snapshot_count = 0
        # the owner-job queue
        self._jobs: queue.Queue[_Job] = queue.Queue()
        self._wake = threading.Event()
        # the snapshot hand-off to the reader thread
        self._pub_lock = threading.Lock()
        self._published: World | None = None
        self._reader_has: World | None = None
        self._reads: queue.Queue[_Read | None] = queue.Queue()
        self._reader: threading.Thread | None = None

    # ---------------------------------------------------------- lifecycle

    @property
    def attached(self) -> bool:
        return self._world is not None

    @property
    def view_frame(self) -> str | None:
        return self._view_frame

    def attach(self, world: World, view_frame: str,
               perceptible: Callable[[World, str, str], bool] | None = None,
               frame_scope: str = "exact") -> None:
        """Bind to a World the host opened, on the host's thread (the pump
        thread). Takes the first snapshot at once. One world per service.
        ``frame_scope`` (FRAME-CONTINUITY-V1 §5) is the scope the host
        configures for its viewers' `state`, `state_union` and `facts`
        (default `exact`); a viewer can never name its own."""
        if frame_scope not in ("exact", "continued", "merged"):
            raise ValueError(f"unknown frame_scope {frame_scope!r}")
        if self._world is not None:
            raise RuntimeError("this service is already attached; detach first")
        if world.buffer.sealed:
            raise ValueError("a read-only snapshot cannot be hosted")
        if not isinstance(view_frame, str) or not view_frame:
            raise ValueError("attach needs a view_frame")
        self._gated = (getattr(world.resolver._model, "_patternbuffer_gated_by", None)
                       is self)             # a read: the service writes no handle
        if not self._gated and self._rate is not None:
            logger.warning(
                "this World's model is not svc.gated(...): the rate cap is inactive, "
                "and a model-bound viewer resolve answers no_rate_cap")
        self._frame_scope = frame_scope
        self._world = world
        self._owner = threading.get_ident()
        self._view_frame = view_frame
        self._perceptible = perceptible
        self._key = None
        self._refresh()
        self._reader = threading.Thread(
            target=self._reader_loop, name="patternbuffer-reader", daemon=True)
        self._reader.start()

    def detach(self) -> None:
        """Release the World. Call it before any close, swap or copy of the
        file. Queued jobs answer `detached`; later calls do too."""
        self._require_owner()
        world, self._world = self._world, None
        self._drain_jobs()
        reader, self._reader = self._reader, None
        if reader is not None:
            self._reads.put(None)
            reader.join(timeout=10)
            if reader.is_alive():
                logger.error("the reader thread did not stop within 10 s")
        with self._pub_lock:
            retired = [w for w in (self._published, self._reader_has) if w is not None]
            self._published = self._reader_has = None
        for snap in {id(w): w for w in retired}.values():
            self._close_quietly(snap)
        self._key = None
        self._owner = None
        del world

    def set_now(self, t: float | None) -> None:
        """The host's coordinate (construct passes `turn_time(n)` as each turn
        commits); viewer writes land here."""
        self._now = t

    def now(self) -> float | None:
        """The coordinate viewer writes land at: the host's `set_now`, else (no
        author) the log's valid-time head as of the last pump."""
        return self._now if self._now is not None else self._valid_head

    def set_view_frame(self, frame: str) -> None:
        """'Play as X', or a world change: later reads and resolves use it."""
        if not isinstance(frame, str) or not frame:
            raise ValueError("a view frame is a non-empty frame name")
        self._view_frame = frame

    def session(self, name: str, role: str = "viewer") -> "Session":
        """A client's door. ``role`` is "viewer", or "recorder" (a viewer that
        may also `record`; the standalone runner only)."""
        if role not in ("viewer", "recorder"):
            raise ValueError(f"unknown role {role!r}")
        if role == "recorder" and not self._standalone:
            raise Refused("record exists on the standalone runner only: under an "
                          "author, play events go to the author")
        return Session(self, name, role)

    # --------------------------------------------------------------- pump

    def _require_owner(self) -> None:
        if self._owner is not None and threading.get_ident() != self._owner:
            raise RuntimeError(
                "the service must be pumped and detached on the thread that "
                "attached it (a World is bound to one thread)")

    def pump(self) -> int:
        """The host's loop: run queued owner jobs, then refresh the viewer
        snapshot if the log moved. Returns the number of jobs run. Call it on
        the attaching thread: while a session waits for input, and after the
        settle."""
        self._require_owner()
        self._wake.clear()
        ran = 0
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break
            ran += self._run_job(job)
        if self._world is not None:
            self._refresh()
        return ran

    def serve_pump(self, stop: threading.Event, interval: float = 0.02) -> None:
        """Pump until ``stop`` is set, waking at once when a job arrives (the
        standalone runner's loop)."""
        while not stop.is_set():
            self.pump()
            self._wake.wait(interval)

    def _run_job(self, job: _Job) -> int:
        with job.lock:
            if job.state != "queued":
                return 0                      # the caller gave up on it
            job.state = "running"
        try:
            if self._world is None:
                job.result = _detached()
            elif job.kind == "resolve":
                job.result = self._do_resolve(**job.args)
            elif job.kind == "record":
                job.result = self._do_record(**job.args)
            else:                              # pragma: no cover - guarded at enqueue
                raise AssertionError(job.kind)
        except BaseException as exc:           # noqa: BLE001 - handed to the caller
            logger.exception("service job %s failed", job.kind)
            job.error = exc
        finally:
            with job.lock:
                job.state = "done"
            job.done.set()
        return 1

    def _drain_jobs(self) -> None:
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            with job.lock:
                if job.state == "queued":
                    job.state = "done"
                    job.result = _detached()
            job.done.set()

    def _submit(self, kind: str, args: dict[str, Any], wait: float) -> Any:
        """Queue an owner job and wait up to ``wait`` seconds for the host's
        next pump to run it. A job that did not run in time is cancelled and the
        call answers `deferred`; a job already running is waited for."""
        if self._world is None:
            return _detached()
        job = _Job(kind, args)
        self._jobs.put(job)
        self._wake.set()
        if not job.done.wait(max(0.0, wait)):
            with job.lock:
                if job.state == "queued":
                    job.state = "cancelled"
                    return {"status": "deferred", "retry_after": self._retry_after}
            job.done.wait()                    # running: let it finish
        if job.error is not None:
            raise job.error
        return job.result

    # ------------------------------------------------------- the snapshot

    def _refresh(self) -> bool:
        """Take a new snapshot iff the committed head or the classifier's
        verdict_version moved since the last one (cadence: an idle session's
        pumps copy nothing)."""
        world = self._world
        assert world is not None
        key = (world.buffer.head(), world.classifier.verdict_version)
        if key == self._key:
            return False
        snap = world.snapshot()
        self.snapshot_count += 1
        self._key = key
        self._valid_head = world.buffer.max_valid_from()
        with self._pub_lock:
            old = self._published
            self._published = snap
            # an old snapshot the reader never took is ours to retire; one it
            # holds is retired by the reader at its next take (it alone uses it)
            if old is not None and old is not self._reader_has:
                self._close_quietly(old)
        return True

    @staticmethod
    def _close_quietly(snap: World) -> None:
        try:
            snap.close()
        except Exception:                      # pragma: no cover - best effort
            logger.exception("closing a retired snapshot failed")

    # --------------------------------------------------------- the reader

    def _take_snapshot(self) -> World | None:
        with self._pub_lock:
            current = self._published
            held = self._reader_has
            if current is not held:
                self._reader_has = current
                if held is not None:
                    self._close_quietly(held)
            return current

    def _reader_loop(self) -> None:
        while True:
            req = self._reads.get()
            if req is None:
                while True:                    # answer anything queued behind us
                    try:
                        late = self._reads.get_nowait()
                    except queue.Empty:
                        return
                    if late is not None:
                        late.result = _detached()
                        late.done.set()
            snap = self._take_snapshot()
            try:
                if snap is None or self._view_frame is None:
                    req.result = _detached()
                else:
                    req.result = _run_read(snap, self._view_frame, req.verb, req.args,
                                       self._frame_scope)
            except BaseException as exc:       # noqa: BLE001 - handed to the caller
                req.error = exc
            finally:
                req.done.set()

    def _read(self, verb: str, args: dict[str, Any]) -> Any:
        if self._world is None or self._reader is None:
            return _detached()
        req = _Read(verb, args)
        self._reads.put(req)
        if not req.done.wait(self._read_timeout):
            raise TimeoutError(f"the reader thread did not answer {verb!r} in "
                               f"{self._read_timeout} s")
        if req.error is not None:
            raise req.error
        return req.result

    # ------------------------------------------------ owner job: resolve

    def _in_view(self, world: World, entity: str, view_frame: str) -> bool:
        """Whether the entity exists in the view frame (some row about a member
        of its identity closure lives in that frame)."""
        members = sorted(world.registry.closure(entity))
        return any(not r.entity.startswith(("a:", ATTR_PREFIX))
                   for r in world.buffer.visible(entity_in=members, frame=view_frame))

    def gated(self, model: Callable[[str, dict], Any]) -> Callable[[str, dict], Any]:
        """The callable a host injects into its World:
        ``World(model=svc.gated(host_callable))``. A pass-through, transparent
        to everything the host does itself, except while a viewer job runs on
        the owner thread: then a call the host's `model_route` sends to the
        model spends the `RateCap`, and over it `_CapExceeded` unwinds the
        job's unit (the job answers `deferred`)."""
        if not callable(model):
            raise TypeError("gated() wraps the host's model callable")
        svc = self

        def gated_model(prompt: str, schema: dict) -> Any:
            if getattr(svc._job, "viewer", False) and svc._rate is not None:
                route = svc._model_route
                if route is None or route(schema) == "model":
                    if not svc._rate.try_acquire():
                        raise _CapExceeded(svc._rate.retry_after())
            return model(prompt, schema)

        gated_model._patternbuffer_gated_by = svc            # type: ignore[attr-defined]
        return gated_model

    def _held(self, world: World, row: Any, view_frame: str) -> bool:
        return any(r.value_type == row.value_type and r.value == row.value
                   for r in world.buffer.visible(entity=row.entity,
                                                 attribute=row.attribute,
                                                 frame=view_frame))

    def _do_resolve(self, entity: str, aspect: str) -> dict:
        world, view_frame = self._world, self._view_frame
        assert world is not None and view_frame is not None
        if not self._in_view(world, entity, view_frame):
            return {"status": "not_perceptible",
                    "reason": "the entity is not in the view frame"}
        if self._perceptible is not None:
            try:
                allowed = bool(self._perceptible(world, entity, aspect))
            except Exception:
                logger.exception("the perceptible hook raised; refusing (fail closed)")
                allowed = False
            if not allowed:
                return {"status": "not_perceptible",
                        "reason": "the host says the player could not perceive it"}
        kind, standing = world.resolver.preview(
            entity, world.canonical_attribute(aspect), CANON)
        if self._perceptible is None and kind == "served" and not all(
                self._held(world, row, view_frame) for row in standing):
            # r5: with no host judging perception, the facts canon already
            # holds are exactly the secrets; only inventing is open
            return {"status": "not_perceptible",
                    "reason": "no host judges what the player could perceive"}
        if (kind == "invent" and self._rate is not None and not self._gated
                and (self._model_route is None
                     or self._model_route({"title": TASK_RESOLVE}) == "model")):
            return {"status": "no_rate_cap"}
        self._job.viewer = True
        try:
            out = world.porcelain.resolve(entity, aspect, frame=CANON,
                                          at=self.now(), perceive_in=view_frame)
        except _CapExceeded as cap:
            return {"status": "deferred",
                    "retry_after": max(cap.retry_after, self._retry_after)}
        except NoModel:
            return {"status": "no_model"}
        except AtomicAbort as abort:
            logger.warning("viewer resolve rolled back (%s)", abort.cause)
            return {"status": "failed", "reason": abort.cause}
        except Exception as exc:
            logger.exception("viewer resolve failed")
            return {"status": "failed", "reason": type(exc).__name__}
        finally:
            self._job.viewer = False
        perceived = out.get("perceived")
        if out["status"] == "resolved" and perceived is not None:
            # the view frame's facts only: the canon rows and their receipt
            # never leave this method
            return {"status": "resolved", "facts": perceived["facts"],
                    "receipt": perceived["receipt"]}
        # unknown / denied / undeclared: the status only (a reason would name
        # canon: the entity's folded kind, a sealed placeholder)
        return {"status": out["status"], "facts": []}

    # --------------------------------------------------- owner job: record

    def _do_record(self, items: list[dict], at: float | None) -> dict:
        world, view_frame = self._world, self._view_frame
        assert world is not None and view_frame is not None
        when = at if at is not None else self.now()
        ops: list[dict] = []
        for item in items:
            base = dict(item)
            if when is not None and not base.get("timeless") and base.get("valid_from") is None:
                base["valid_from"] = when
            # the frame and the status are the service's, written twice: once
            # in canon, once in the view frame
            for frame in (CANON, view_frame):
                ops.append({"op": "assert",
                            "item": {**base, "frame": frame, "status": "observed"}})
        try:
            receipt = world.porcelain.commit_set(ops, classify="rules")
        except AtomicAbort as abort:
            return {"status": "refused", "cause": abort.cause,
                    "skipped": abort.skipped, "error": abort.error}
        return {"status": "recorded", "receipt": receipt.to_dict()}


# ------------------------------------------------------------- viewer reads


def _exists_in_view(world: World, ident: str, view_frame: str,
                    asserted_as_of: Any) -> bool:
    """Whether some row about a member of the id's identity closure lives in
    the view frame (existence is perspectival, WORLD-SERVICE-V1 §3 r5)."""
    members = sorted(world.registry.closure(ident))
    return any(not r.entity.startswith(("a:", ATTR_PREFIX))
               for r in world.buffer.visible(entity_in=members, frame=view_frame,
                                             asserted_as_of=asserted_as_of))


def _snapshot_perspectival(world: World, view_frame: str, call: dict) -> Any:
    """`snapshot(scope)` treats an id as known when it lives in the frame OR in
    canon, so its error shape would tell a viewer which ids canon holds. Here an
    id with no row in the view frame is `bad` exactly as an id that exists
    nowhere (the engine's own error text, from a probe of an absent id)."""
    scope = call.get("scope")
    roots = [scope] if isinstance(scope, str) else scope
    if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
        return dispatch(world, "snapshot", call)["result"]      # engine's own error
    aao = call.get("asserted_as_of")
    bad = [r for r in roots
           if not ID_RE.fullmatch(r) or not _exists_in_view(world, r, view_frame, aao)]
    if not bad:
        return dispatch(world, "snapshot", call)["result"]
    probe = dispatch(world, "snapshot", {**call, "scope": ["zz:absent_probe"]})["result"]
    error = probe.get("error") if isinstance(probe, dict) else None
    return {"error": error or "snapshot scope must be KNOWN entity ids "
                              "(use ask for references)", "bad": bad}


def _make_adapter(verb: str) -> Callable[..., Any]:
    """The per-verb adapter: refuse a caller frame, force the pinned
    parameters, inject the view frame, then MCP's `dispatch`."""
    params = set(inspect.signature(getattr(Porcelain, verb)).parameters)
    takes_frame = "frame" in params
    takes_scope = "frame_scope" in params     # state, state_union, facts
    forced = {p: v for (v_, p), v in _VIEWER_FORCED.items() if v_ == verb}
    # MCP's `dispatch` fills FORCED_PARAMS itself (and refuses a caller's); the
    # service adds only what MCP does not force
    inject = {p: v for p, v in forced.items() if (verb, p) not in FORCED_PARAMS}

    def adapter(world: World, view_frame: str, args: dict,
                frame_scope: str = "exact") -> Any:
        for name in _REFUSED_ARGS:
            if name in args:
                raise Refused(
                    f"{verb}: a viewer cannot name {name!r}; reads are of the "
                    "player's view only")
        for name in forced:
            if name in args:
                raise Refused(f"{verb}: {name!r} is forced by the service")
        call = {**args, **inject}
        if takes_frame:
            call["frame"] = view_frame
        if takes_scope:
            call["frame_scope"] = frame_scope        # the host's, never the caller's
        if verb == "snapshot":
            return _snapshot_perspectival(world, view_frame, call)
        return dispatch(world, verb, call)["result"]

    adapter.__name__ = f"viewer_{verb}"
    return adapter


ADAPTERS: dict[str, Callable[..., Any]] = {
    verb: _make_adapter(verb) for verb in VIEWER_READS}

assert set(VIEWER_READS) <= set(V1_READS)       # the allowlist is a subset of MCP's


def _run_read(snap: World, view_frame: str, verb: str, args: dict,
              frame_scope: str = "exact") -> Any:
    return ADAPTERS[verb](snap, view_frame, args, frame_scope)


# ------------------------------------------------------------------ session


class Session:
    """A client's door onto the service. ``call(verb, **args)``:

    - a `VIEWER_READS` verb, served from the snapshot, always in the view frame;
    - `resolve(entity, aspect, wait=)`, pinned to canon for the plant and the
      view frame for the perception;
    - `now()`;
    - `record(items, at=)`, for a recorder on the standalone runner.
    """

    def __init__(self, service: WorldService, name: str, role: str) -> None:
        self.service = service
        self.name = name
        self.role = role

    def call(self, verb: str, **args: Any) -> Any:
        svc = self.service
        if verb in ADAPTERS:
            for refused in _REFUSED_ARGS:
                if refused in args:
                    raise Refused(
                        f"{verb}: a viewer cannot name {refused!r}; reads are of the "
                        "player's view only")
            return svc._read(verb, args)
        if verb == "resolve":
            return self._resolve(**_only(args, "resolve", {"entity", "aspect", "wait"},
                                         required={"entity", "aspect"}))
        if verb == "now":
            _only(args, "now", set())
            return {"now": svc.now()}
        if verb == "record":
            if self.role != "recorder":
                raise Refused("record needs a recorder session on the standalone runner")
            return self._record(**_only(args, "record", {"items", "at"},
                                        required={"items"}))
        if verb in VIEWER_EXCLUDED:
            raise Refused(f"{verb} is not a viewer verb ({VIEWER_EXCLUDED[verb]})")
        raise Refused(f"unknown verb {verb!r}")

    def _resolve(self, entity: Any, aspect: Any, wait: Any = DEFAULT_WAIT) -> dict:
        if not (isinstance(entity, str) and entity and isinstance(aspect, str) and aspect):
            raise Refused("resolve needs a string entity and a string aspect")
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or wait < 0:
            raise Refused("wait is a non-negative number of seconds")
        return self.service._submit("resolve", {"entity": entity, "aspect": aspect},
                                    float(wait))

    def _record(self, items: Any, at: Any = None) -> dict:
        if not isinstance(items, list) or not items:
            raise Refused("record needs a non-empty list of items")
        if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float))):
            raise Refused("at is a number")
        clean = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise Refused(f"record item {i} is not an object")
            if "frame" in item or "status" in item:
                raise Refused(
                    f"record item {i} names its own frame/status: the service "
                    "sets both (canon and the view frame, observed)")
            extra = set(item) - _RECORD_KEYS
            if extra:
                raise Refused(f"record item {i} carries keys a play event may not: "
                              f"{sorted(extra)}")
            entity, attribute = item.get("entity"), item.get("attribute")
            if (not isinstance(entity, str) or not isinstance(attribute, str)
                    or entity.startswith(("a:", ATTR_PREFIX))
                    or attribute in _RECORD_BARRED_ATTRIBUTES):
                raise Refused(f"record item {i} is not a play event (its subject or "
                              "attribute is bookkeeping)")
            if item.get("value_type", "literal") not in _RECORD_VALUE_TYPES:
                raise Refused(f"record item {i}: value_type must be one of "
                              f"{sorted(_RECORD_VALUE_TYPES)}")
            clean.append(dict(item))
        return self.service._submit(
            "record", {"items": clean, "at": at}, DEFAULT_WAIT)


def _only(args: dict, verb: str, allowed: set[str], required: set[str] = frozenset()) -> dict:
    for refused in _REFUSED_ARGS + ("perceive_in", "at"):
        if refused in args and refused not in allowed:
            raise Refused(f"{verb}: a caller cannot name {refused!r}")
    unknown = set(args) - allowed
    if unknown:
        raise Refused(f"{verb}: unknown argument(s) {sorted(unknown)}")
    missing = required - set(args)
    if missing:
        raise Refused(f"{verb}: missing argument(s) {sorted(missing)}")
    return args


# ---------------------------------------------------------------- the runner


def make_runner_callable(generator: Callable[[str, dict], Any] | None
                         ) -> tuple[Callable[[str, dict], Any], Callable[[dict], str]]:
    """The runner's model callable and its route. With a ``generator`` (the
    host-supplied `(prompt, schema) -> json` code route, reading
    `task_request(schema)`), resolve calls go to it; everything else, and every
    resolve with no generator, raises `NoModel`, which the service reports as
    `{"status": "no_model"}`."""

    def route(schema: dict) -> str:
        return "code" if generator is not None and schema.get("title") == TASK_RESOLVE \
            else "model"

    def model(prompt: str, schema: dict) -> Any:
        if route(schema) == "code":
            return generator(prompt, schema)
        raise NoModel("the standalone runner has no model: pass --generator")

    return model, route


def _load_generator(spec: str) -> Callable[[str, dict], Any]:
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError(f"--generator wants MODULE:FN, got {spec!r}")
    fn = getattr(importlib.import_module(module_name), attr)
    if not callable(fn):
        raise ValueError(f"{spec} is not callable")
    return fn


class Runner:
    """The standalone host: opens the World, attaches a service with
    ``standalone=True`` and pumps it on its own thread, serving sessions over
    localhost HTTP + JSON (standard library only)."""

    def __init__(self, open_world: Callable[[Callable], World], view_frame: str, *,
                 port: int = 0, recorders: tuple[str, ...] = (),
                 rate: RateCap | None = None,
                 model_route: Callable[[dict], str] | None = None) -> None:
        # A World is bound to the thread that opened it, so the runner opens
        # it ON its pump thread (the owner thread) and closes it there.
        # `open_world(gated)` builds it with `model=gated(host_callable)`.
        self._open_world = open_world
        self.world: World | None = None
        self.recorders = frozenset(recorders)
        self.service = WorldService(model_route=model_route, rate=rate,
                                    standalone=True)
        self._view_frame = view_frame
        self._stop = threading.Event()
        self._sessions: dict[str, Session] = {}
        self._sessions_lock = threading.Lock()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        # 127.0.0.1 only: wider hosting is not built here (WORLD-SERVICE-V1 §9)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(self))
        self.httpd.daemon_threads = True
        self.port: int = self.httpd.server_address[1]
        self._pump_thread = threading.Thread(
            target=self._pump_main, name="patternbuffer-pump", daemon=True)
        self._http_thread = threading.Thread(
            target=self.httpd.serve_forever, name="patternbuffer-http", daemon=True)

    # the World is opened by the caller, but must be USED on one thread: the
    # pump thread attaches, pumps and detaches, so it is the owner thread.
    def _pump_main(self) -> None:
        try:
            self.world = self._open_world(self.service.gated)
            self.service.attach(self.world, self._view_frame)
        except BaseException as exc:           # noqa: BLE001
            self._startup_error = exc
            if self.world is not None:
                self.world.close()
            self._ready.set()
            return
        self._ready.set()
        try:
            self.service.serve_pump(self._stop)
        except Exception:
            logger.exception("the pump loop died")
        finally:
            self.service.detach()
            self.world.close()

    def start(self) -> "Runner":
        self._pump_thread.start()
        self._ready.wait(30)
        if self._startup_error is not None:
            self.httpd.server_close()
            raise self._startup_error
        self._http_thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self.service._wake.set()
        if self._http_thread.is_alive():
            self.httpd.shutdown()
        self.httpd.server_close()
        self._pump_thread.join(timeout=30)
        self._http_thread.join(timeout=30)

    def session(self, name: str) -> Session:
        with self._sessions_lock:
            sess = self._sessions.get(name)
            if sess is None:
                role = "recorder" if name in self.recorders else "viewer"
                sess = self._sessions[name] = self.service.session(name, role=role)
            return sess


_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


def _handler_for(runner: Runner) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "patternbuffer-service"

        def log_message(self, fmt: str, *args: Any) -> None:    # route to logging
            logger.debug("http %s", fmt % args)

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self) -> bool:
            # a browser page on another origin cannot read our answers, but a
            # rebinding name could still reach us: only loopback names are served
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in _LOOPBACK_HOSTS

        def do_GET(self) -> None:                                # noqa: N802
            if not self._host_ok():
                return self._send(403, {"error": {"type": "forbidden",
                                                  "message": "loopback hosts only"}})
            path = self.path.split("?", 1)[0]
            if path == "/now":
                return self._send(200, {"now": runner.service.now()})
            if path == "/changes":
                return self._send(501, {"error": {"type": "not_implemented",
                                                  "message": "the changes feed is S2"}})
            self._send(404, {"error": {"type": "not_found", "message": self.path}})

        def do_POST(self) -> None:                               # noqa: N802
            if not self._host_ok():
                return self._send(403, {"error": {"type": "forbidden",
                                                  "message": "loopback hosts only"}})
            if self.path.split("?", 1)[0] != "/call":
                return self._send(404, {"error": {"type": "not_found",
                                                  "message": self.path}})
            # JSON only: a cross-origin page cannot send this type without a
            # preflight, which this server never grants
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() \
                    != "application/json":
                return self._send(415, {"error": {"type": "unsupported_media_type",
                                                  "message": "send application/json"}})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if not 0 < length <= 4_000_000:
                    raise ValueError("body size")
                body = json.loads(self.rfile.read(length))
                name, verb = body["session"], body["verb"]
                args = body.get("args") or {}
                if not (isinstance(name, str) and name and isinstance(verb, str)
                        and isinstance(args, dict)):
                    raise ValueError("shape")
            except (ValueError, KeyError, TypeError):
                return self._send(400, {"error": {
                    "type": "bad_request",
                    "message": "POST /call wants {session, verb, args}"}})
            try:
                result = runner.session(name).call(verb, **args)
            except Refused as exc:
                return self._send(400, {"error": {"type": "refused", "message": str(exc)}})
            except (ValueError, TypeError) as exc:
                return self._send(400, {"error": {"type": "bad_request",
                                                  "message": str(exc)}})
            except TimeoutError as exc:
                return self._send(504, {"error": {"type": "timeout", "message": str(exc)}})
            except Exception as exc:
                logger.exception("call %s failed", verb)
                return self._send(500, {"error": {"type": type(exc).__name__,
                                                  "message": "see the service log"}})
            self._send(200, {"result": result})

    return Handler


def main(argv: list[str] | None = None) -> int:
    """`python -m patternbuffer.service --world PATH --world-id ID --view-frame F`."""
    parser = argparse.ArgumentParser(
        prog="patternbuffer-service",
        description="Host one pattern-buffer world for every module: localhost "
                    "HTTP + JSON, the player's view only. One service, one world "
                    "(the 1:1 invariant).")
    parser.add_argument("--world", required=True, help="path to the .world file")
    parser.add_argument("--world-id", required=True, help="the world's id")
    parser.add_argument("--view-frame", required=True,
                        help="the player's frame, e.g. knows:person:mara")
    parser.add_argument("--port", type=int, default=8787,
                        help="localhost port (0 picks a free one)")
    parser.add_argument("--generator", default=None, metavar="MODULE:FN",
                        help="a code generator `(prompt, schema) -> json` that "
                             "answers resolve calls (read task_request(schema)); "
                             "without it, model-routed resolves answer no_model")
    parser.add_argument("--recorder", action="append", default=[], metavar="NAME",
                        help="a session name that may `record` (repeatable)")
    parser.add_argument("--policy", choices=sorted(POLICIES), default=None)
    parser.add_argument("--rate", type=int, default=None, metavar="N",
                        help="cap model-routed viewer resolves at N per minute")
    args = parser.parse_args(argv)

    generator = _load_generator(args.generator) if args.generator else None
    model, route = make_runner_callable(generator)
    runner = Runner(lambda gated: World(args.world, world_id=args.world_id,
                                        model=gated(model), policy=args.policy),
                    args.view_frame, port=args.port,
                    recorders=tuple(args.recorder),
                    rate=RateCap(args.rate) if args.rate is not None else None,
                    model_route=route)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    runner.start()
    logger.info("serving %s on http://127.0.0.1:%d", args.world, runner.port)
    print(f"patternbuffer-service: http://127.0.0.1:{runner.port}", flush=True)
    try:
        stop.wait()
    finally:
        runner.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
