# WORLD-SERVICE-V1: one world, every module

**Status:** r2. It folds in construct's shape read (m53b6e8) and goes to pbr for spec review. Author: pb,
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
   - At every `pump()` that follows a commit, the owner thread makes an **in-memory snapshot** of
     the world with SQLite's backup API (§7) and hands it to the service's **reader thread**.
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
   - **viewer**:
     - It may use the read verbs only (MCP's `V1_READS`), served from the snapshot. Every
       frame-taking read is **forced to the current `view_frame`**; a viewer that names a frame is
       refused. So a viewer never reads canon.
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
   - **The job** resolves in **canon** (invention is canon's), then **mirrors the generated rows
     into the view frame** as the player's perception: `observed`, at `now`. Construct switches
     `furnish_scene` to `observed` in the same change (answer 3), so both paths agree. The plant,
     force and mirror run as one atomic unit.
   - **The viewer receives** the view-frame facts only.
   - **Refusals:**
     - `{"status": "not_perceptible", "reason": ...}` when the hook or the view frame refuses;
     - `{"status": "deferred", "retry_after": s}` when the job did not run within the call's wait;
       for example, mid-turn, until the next pump. That should be rare, because construct
       pre-resolves at scene open.
5. **The recorder's `record(items, at=)`** exists only on the standalone runner (no author). It
   writes play events as `observed` rows through the gate, in canon and in the view frame. Under an
   author, play events go to the author (construct), as agreed. A world has exactly one writer of
   play.
6. **One "now", and the view frame.**
   - The host calls `set_now(t)` as each turn commits. Construct passes `turn_time(n)`, so between
     turns, viewer writes land at the last played turn.
   - With no author, `now` is `axis_heads()["valid_head"]`.
   - `view_frame` is given at `attach` and changed with `set_view_frame` (construct, change 2). The
     protagonist differs per world and per "play as X", so there is no constant default.
7. **The one engine addition: `World.snapshot()`.** It returns a **read-only World over an
   in-memory copy** of this world, made with SQLite's backup API from the owner's connection, on the
   owner's thread.
   - The copy's buffer refuses every append and commit (`ReadOnlyWorld`).
   - Its derived caches are its own, built on first use.
   - It may be handed to one other thread (`check_same_thread=False`, used by one thread at a time).
   - Nothing about the source World changes.
   - A host can also use it directly for any off-thread read.
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

- No existing engine verb, row shape or read answer changes. The one engine addition is
  `World.snapshot()` (§7), which is additive.
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
1a. `World.snapshot()` is read-only: every write raises `ReadOnlyWorld`. It answers reads
    identically to its source at the moment it was taken, verified on copies of construct's worlds.
    The source sees no second connection, and `SecondWriter` never trips.
1b. A viewer read during a long author job returns at once from the last snapshot.
2. A viewer cannot read canon: every frame-taking read is forced, and naming a frame is refused.
3. A viewer's resolve:
   - is refused when the entity is absent from the view frame;
   - plants, forces and mirrors in one unit;
   - is memoized;
   - is rate-capped (deferred, with nothing written);
   - is never capped for a code route.
4. `record` exists only with `author=False`, and writes `observed` rows to canon and the view frame.
5. `now`: viewer writes land at the author's coordinate.
6. The runner: a localhost-only bind, with an HTTP round trip for read, resolve and record.
7. With no service in use, the suite is byte-identical.
