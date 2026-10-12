# WORLD-SERVICE-V1: one world, every module

**Status:** r4. It closes pbr's r3 RED, the one remaining authorization gap: a frame supplied by
the caller on `resolve` and `record` (§4, §5), plus joining narrowed to the `perceive_in` path
(§7b). r3 answered pbr's r2 RED (§3, §4, §7) and folded in the snapshot cadence (§2). Earlier rounds folded in construct's shape read (m53b6e8). Author: pb,
2026-10-12.
**Source:** roadmap R39, S1 of `specs/proposals/UNIFIED-WORLD-ACCESS.md`, approved by Kabe on
2026-10-12 (gate gde97f3).
**Builds on:** E2 (`ResolveRequest`), E1 (`resolvable_for`), SECOND-WRITER (one live World per file),
MCP-WRAPPER-V1 (the verb registry and its dispatch).

## Need

The agreed structure (§1, §2, §5, §8 of the proposal) says:
- one host per world, as a library class shipped in this repo and **outside the engine core**;
- whoever opens the world hosts it; today that is construct;
- other modules read through **the player's view, never raw canon**, and may ask for an undecided
  detail;
- renderers write nothing;
- a world with no author (holo-emitter playing alone) needs a door to record play events;
- model-routed resolves are capped, so a renderer cannot fan out calls.

Two facts shape the design:
- A `World` is thread-bound, and a second connection to its file now raises `SecondWriter`. Every
  call must therefore run on the one thread that opened it.
- Construct makes many reads per turn in-process. Moving each read across a queue would add latency
  to every one.

## The shape (r2, after construct's shape read m53b6e8)

`patternbuffer.service`: a new module. The engine core never imports it, apart from the one engine
addition in §7.

```python
svc = WorldService(model_route=None, rate=RateCap(...))   # no World yet
svc.attach(world, view_frame="knows:person:mara",          # the host opened it, the host owns it
           perceptible=hook)                               # host closure, §4
svc.pump()             # the host's loop: run queued jobs, refresh the viewer snapshot
svc.set_now(t)         # the host's coordinate, §6
svc.set_view_frame(f)  # "play as X", or a world change
svc.detach()           # before any close, swap or copy of the file
svc.session("holo-emitter", role="viewer")   # a client's door, §3
```

1. **The host owns the World; the service attaches** (construct, answer 1).
   - Construct already owns each World's whole lifecycle: builds open, close and delete worlds; slot
     copies; atomic file swaps; one playthrough per session; the settle on the session thread; and
     many sessions per process.
   - The service takes none of that. `attach(world)` binds it to a World the host opened, on the
     host's thread. Every job that needs the World runs inside `pump()`, which the host calls from
     that same thread. The one-handle and one-thread rules hold by construction.
   - `detach()` comes before any close, swap or copy. A job queued after `detach` gets
     `{"status": "detached"}`.
   - **Pump points (construct's):** while a session waits for player input, which is most of the
     wall clock, and after the settle.
   - **The standalone runner** (§8) attaches and pumps on its own loop, so with no author the
     service runs itself.
2. **Viewer reads never wait on a turn** (construct, change 1). A turn's engine work is interleaved
   with model calls, and run 5 measured 41–209 s player-felt per turn. So viewer reads are not owner
   jobs:
   - At `attach`, and then at a `pump()` only when the **committed log head** has moved since the
     last snapshot, the owner thread makes an **in-memory snapshot** of the world with SQLite's
     backup API (§7) and hands it to the service's **reader thread**.
     - *(r3, pbr)* The key is the committed head, not `log_version`, which also moves on a rollback
       or a cache invalidation and would recopy an unchanged log.
     - Sidecar-only changes (a later classification of an existing row, e.g. a deferred batch)
       also trigger a snapshot. The classifier gains an in-memory `verdict_version` counter,
       bumped at each of its verdict-write sites, never stored. The refresh key is
       `(committed head, verdict_version)`. Without it, a viewer could read a stale class until the
       next commit.
     - Construct's play worlds are 1.5–4 MB, so a snapshot is cheap, and an idle session's pumps
       copy nothing.
   - Viewer reads run on the reader thread against the newest snapshot. They never touch the file,
     never block a writer, and never trip `SecondWriter`: the snapshot is another database, not
     another connection to the file.
   - A viewer sees the world as of the last pump: the last committed turn or settle. That is the
     "snapshot of the last commit" construct asked for.
   - **Why not a second read-only connection on the file:** construct's worlds use SQLite's
     rollback journal (`journal_mode=delete`). A live reader there holds locks that can stall the
     author's commits. Switching to WAL would put a world's committed rows in a side file, which
     breaks construct's file copies and atomic swaps.
3. **The client door: `session(name, role)`.** A session exposes `call(verb, **args)`, validated
   through MCP-WRAPPER-V1's registry and its `dispatch`, with one rule set per role:
   - **viewer** *(r3: an explicit allowlist, not MCP's `V1_READS`)*:
     - **`VIEWER_READS`**, served from the snapshot, each through a per-verb adapter. The adapter
       **refuses** a caller-supplied `frame` and **injects** the current `view_frame`:
       - `snapshot`, `state`, `state_union`, `where`, `aggregate`, `confidence`;
       - `locate`, `contents`, `composition`, `features`, `path`, `route`;
       - `neighborhood`, `salience`, `events`, `in_transit`, `entities`;
       - `facts`, with `include_meta` forced False;
       - `refer`, with `model` and `learn` forced False, as over MCP;
       - `canonical_attribute`, which reads vocabulary only and takes no frame.
     - **Excluded**, because each reads across frames or reports canon or global identity state:
       - `frame_diff`, which takes two arbitrary frames;
       - `who_knows`, which reports every `knows:*` frame;
       - `proposals`, `identity_conflicts`, `typing_conflicts`, `correlations` and
         `correlation_conflicts`, which are canon identity diagnostics;
       - `fidelity_audit`, a diagnostic;
       - `axis_heads`, which reports global log positions; a viewer gets `now` instead.
     - A verb added to the porcelain later is excluded until it is classified here. The allowlist is
       explicit, never reflected.
     - It may use `resolve` (§4), `now`, and `changes(since)` once S2 builds it.
   - **recorder**: a viewer that may also use `record(items, at=)` (§5), on the standalone runner
     only.
   - The author does not use a session. It calls the World directly on its own thread, as today.
4. **A viewer's resolve** is an owner job, so it runs at the next `pump()`.
   - **It is allowed only where the player could perceive it.** The entity must exist in the view
     frame, and the host's `perceptible(world, entity, aspect) -> bool` must agree.
     - Construct's hook is a closure over the session: the entity sits transitively in the player's
       current place, it is not inside a closed container, and `(entity, aspect)` is not among the
       arc's protected keys (`construct/arc/concealment.py`). A viewer must never invent what the
       hidden arc turns on.
     - With no hook supplied, the entity existing in the view frame is enough.
   - **No caller frame** *(r4)*. A viewer's `resolve` takes `entity`, `aspect` and an optional
     wait, and nothing else. A caller-supplied `frame` or `perceive_in` is **refused**, not
     ignored. The service always calls exactly `frame=CANON, perceive_in=<current view_frame>`, so
     no caller can force a hidden frame's placeholder or constraint, or mirror it into the view.
   - **The job** calls the engine's resolve with **`perceive_in=view_frame`** (§7b). In **one**
     atomic unit, it:
     - plants if needed (E1);
     - forces the placeholder, or serves the memo;
     - mirrors the resolved rows into the view frame as the player's perception: `observed`, at
       `now`, through the gate.

     A failure anywhere, including a mirror refused at the gate, rolls back everything: no
     placeholder, no generated row, no mirror. A memoized resolve mirrors only the rows the view
     frame does not already hold, so repeated asks write nothing new. Construct switches
     `furnish_scene` to `observed` in the same change (answer 3), so both paths agree.
   - **The viewer receives** the view-frame facts only.
   - **Refusals:**
     - `{"status": "not_perceptible", "reason": ...}` when the hook or the view frame refuses;
     - `{"status": "deferred", "retry_after": s}` when the job did not run within the call's wait;
       for example, mid-turn, until the next pump. That should be rare, because construct
       pre-resolves at scene open.
5. **The recorder's `record(items, at=)`** exists only on the standalone runner (no author). It
   writes play events as `observed` rows through the gate, in canon and in the view frame.
   - *(r4)* An item carrying its own `frame` key is **refused**, and the whole call writes nothing.
     The gate treats `frame=` as a default that item keys override, so stripping alone would hide a
     malicious caller.
   - A caller-supplied `status` is refused the same way.
   - The service writes each item twice, both times with the frame and status it sets itself: once
     in canon, once in `view_frame`. Both writes are one atomic unit. Under an
   author, play events go to the author (construct), as agreed. A world has exactly one writer of
   play.
6. **One "now", and the view frame.**
   - The host calls `set_now(t)` as each turn commits. Construct passes `turn_time(n)`, so between
     turns, viewer writes land at the last played turn.
   - With no author, `now` is `axis_heads()["valid_head"]`.
   - `view_frame` is given at `attach` and changed with `set_view_frame` (construct, change 2). The
     protagonist differs per world and per "play as X", so there is no constant default.
7. **Three engine additions** *(r3: r2 claimed one)*.

   **(a) `World.snapshot()`: a read-only World over an in-memory copy.**
   - The owner thread backs the source up into a fresh in-memory connection opened with
     `check_same_thread=False`.
   - A `World` is then **constructed normally over that copy**. Construction runs schema setup, the
     classifier's sidecar `INSERT OR IGNORE` and its commits. All of those land in the **copy**,
     never the source.
   - Only then is the copy's **log sealed**: the buffer's append, the gate, retraction and every
     unit refuse with `ReadOnlyWorld`.
   - Derived sidecar tables in the copy (classification, salience) stay writable. They are the
     snapshot's own disposable derived layer, like its in-memory caches. The salience read, for one,
     writes its sidecar on demand.
   - The invariant is about the log. After construction and any reads:
     - the copy's `assertions` and `world_meta` tables are row-for-row identical to the source's at
       backup time;
     - the source's file and `data_version` are untouched.
   - The snapshot is handed to one other thread and used by that thread only.

   **(b) The resolve seam: `resolve(entity, aspect, frame=CANON, at=None, perceive_in=None)`** on
   the porcelain and the World.
   - With `perceive_in` set, the plant, the force (or memo) and the mirror run in **one** unit.
   - **Joining is exclusive to this path** *(r4)*. Only the `perceive_in` call opens the outer unit,
     and only inside it does the resolver's plant-and-force run as part of that unit, through an
     explicit internal flag. It does not use a general rule that units nest.
   - The outer unit owns the commit and the rollback.
   - Everywhere else, a nested `atomic_unit` is still refused exactly as before. Without
     `perceive_in`, behaviour is byte-identical to E1, including that refusal.

   **(c)** The classifier's in-memory `verdict_version` counter (§2). It is additive and never
   stored.
8. **The rate cap.** `RateCap` wraps the model callable for viewer-initiated resolve jobs only.
   - It counts only calls the host's `model_route(schema) -> "code" | "model"` sends to the model.
     Construct's `engine_callable` already sees the schema before any transform, so it can read
     `task_request(schema)` there.
   - Over the cap, a viewer's resolve returns `deferred` and writes nothing.
   - Author work is never capped: the author owns its own budget.
9. **The runner.** `python -m patternbuffer.service --world PATH --world-id ID --view-frame F
   [--port N] [--generator MODULE:FN]`.
   - It opens the World itself, attaches and pumps on its own loop. It serves sessions over
     **localhost HTTP + JSON** using only the standard library: `POST /call {session, verb, args}`,
     `GET /now`, and `GET /changes?since=` (S2).
   - It binds 127.0.0.1 only. Wider hosting (a phone, the public site) is Kabe's call and is not
     built here.
   - With no `--generator`, model-routed resolves return `{"status": "no_model"}`.

## What does not change

- No existing engine verb, row shape or read answer changes. The engine additions in §7 are all
  additive: `World.snapshot()`, `resolve(perceive_in=)` with a joining unit, and `verdict_version`.
- A host that never constructs a `WorldService` or calls `snapshot()` sees nothing new.
- MCP-WRAPPER-V1's server is untouched. Its registry and `dispatch` are reused, not copied.

## Not in scope

- **S2:** the view export and the `changes(since)` feed for offline mirrors.
- **E3.**
- **The transport to phones** and **holo-bridge** (Kabe's).
- **Multi-world hosting:** one service, one world (the 1:1 invariant).

## Construct's answers (m53b6e8), folded in above

| Question | Answer | Where |
|---|---|---|
| (1) | attach + pump, not run(fn) | §1 |
| (2) | the hook is a session closure: transitive containment in the current place, not in a closed container, not an arc-protected key | §4 |
| (3) | `observed`; construct switches `furnish_scene` too | §4 |
| change 1 | viewer reads never wait on a turn | §2, §7 |
| change 2 | `view_frame` set at attach and changeable | §6 |

## Checks (for the build)

1. Every owner job runs inside `pump()` on the attaching thread, so one connection writes. After
   `detach`, jobs return `detached`.
1a. `World.snapshot()`:
    - every log write raises `ReadOnlyWorld`;
    - construction and first reads (including `salience`) leave the copy's `assertions` and
      `world_meta` identical to the source's, and leave the source untouched (file bytes and
      `data_version`);
    - it answers every `VIEWER_READS` verb identically to its source at backup time, on copies of
      construct's worlds;
    - `SecondWriter` never trips.
1c. Snapshot cadence: no copy when the committed head and the sidecar version are unchanged, and a
    copy after a commit or a sidecar change.
1b. A viewer read during a long author job returns at once from the last snapshot.
2. A viewer cannot read canon or another frame:
   - naming `frame="canon"` or a second `knows:` frame is refused on every `VIEWER_READS` verb;
   - every excluded verb is refused;
   - a test walks the porcelain's verbs and fails on any verb that is neither allowlisted nor
     excluded, so a new verb cannot slip through.
3. A viewer's resolve:
   - is refused when the entity is absent from the view frame;
   - plants, forces and mirrors in one unit, and a mirror refused at the gate rolls back the plant
     and the force (pbr r2);
   - a memoized resolve mirrors nothing it already holds;
   - **malicious frames** *(r4)*: a viewer `resolve` with `frame="canon"`, a second `knows:` frame
     or `perceive_in=` is refused and writes nothing. A placeholder planted only in a hidden frame is
     never forced through a viewer;
   - is memoized;
   - is rate-capped (deferred, with nothing written);
   - is never capped for a code route.
4. `record` exists only on the standalone runner, and writes `observed` rows to canon and the view
   frame in one unit. *(r4)* An item with its own `frame` or `status` key is refused, and the whole
   call writes nothing.
4a. A nested `atomic_unit` outside `perceive_in` is still refused (the existing test stands
    unchanged).
5. `now`: viewer writes land at the author's coordinate.
6. The runner: a localhost-only bind, with an HTTP round trip for read, resolve and record.
7. With no service in use, the suite is byte-identical.
