# WORLD-SERVICE-V1: one world, every module

**Status:** r1 draft. It goes to construct (the host) for a shape read, then to pbr. Author: pb,
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

## The shape

`patternbuffer.service`: a new module. The engine core never imports it.

```python
svc = WorldService(path, world_id, model=callable, policy=None,
                   view_frame="knows:person:player",
                   rate=RateCap(per_minute=..., per_session=...),
                   perceptible=None)          # host hook, §4
svc.start()                                   # owns the World on its own thread
svc.run(lambda w: ...)                        # author: one closure, many calls, one hop
svc.session("holo-emitter", role="viewer")    # a client's door, §3
svc.stop()
```

1. **One owner thread.** `start()` opens the `World` on a dedicated thread, which then serves a FIFO
   queue of jobs. Every job runs on that thread, so writes are serialized and the one-handle rule
   holds by construction.
2. **The author's door: `run(fn)`.**
   - The author submits a closure. It runs on the owner thread with the `World` and returns its
     result (a future, or a blocking `run`).
   - Construct wraps a turn's engine work in one closure, so a turn costs one hop, not one per read.
     Other clients' jobs interleave only between closures, never inside one.
   - The author may call any porcelain verb. No restriction applies: the author is the world's
     principal, as an MCP client is today.
3. **The client door: `session(name, role)`.** A session exposes `call(verb, **args)`, validated
   through MCP-WRAPPER-V1's registry and its `dispatch`, with one rule set per role:
   - **viewer**:
     - It may use the read verbs only (MCP's `V1_READS`). Every frame-taking read is **forced to
       the service's `view_frame`**; a viewer that names a frame is refused. So a viewer never reads
       canon.
     - It may use `resolve` (§4) and `axis_heads`. It may use `changes(since)` once S2 builds it.
   - **recorder**: a viewer that may also use `record(items, at=)` (§5). It exists only on a
     service started with `author=False`.
   - **author**: everything, including `run(fn)`.
4. **A viewer's resolve.** It may ask for an undecided detail only where the player could perceive
   it:
   - The entity must exist in the view frame (it has at least one visible row there), and the
     host's `perceptible(world, entity, aspect) -> bool` hook must agree. With no hook supplied, the
     entity existing in the view frame is enough.
   - The service then calls `resolve` in **canon** (invention is canon's) and **mirrors the
     generated rows into the view frame** as the player's perception: the same items through the
     gate into `view_frame`, at the resolve's `at`, exactly as construct's `furnish_scene`
     (`turnloop.py:1986`) does today, with the gate's default status. This lifts that pattern into the
     service, so every module gets it. The viewer receives the view-frame facts, never the canon ids of anything
     else.
   - A refused resolve returns `{"status": "not_perceptible", "reason": ...}`. The plant, the force
     and the mirror run as one job, in one atomic unit, so a failure leaves nothing.
   - `at` defaults to the author's published coordinate (§6).
5. **The recorder's `record(items, at=)`.** It writes play events as `observed` rows through the
   ordinary gate: canon for physical state, plus the same rows in the view frame. It runs only when
   no author holds the world (`WorldService(..., author=False)`), so a world has exactly one writer
   of play. Under an author, play events go to the author (construct), as agreed.
6. **One "now".** The service publishes `now`, the author's coordinate:
   - `svc.set_now(t)` is called by the author, typically at the end of a turn;
   - without an author it is `axis_heads()["valid_head"]`.

   Viewer resolves and records land at `now` unless the author passes `at`. This answers construct's
   point 3: a resolve between turns never folds out of order.
7. **The rate cap.** `RateCap` wraps the model callable the service hands its `World`.
   - It counts only calls that reach a model: a `patternbuffer_resolve` call whose request the host
     routes to the model, plus every non-resolve task.
   - **Routing stays the host's:** the service takes an optional `route(schema) -> "code" | "model"`,
     and only `"model"` counts.
   - Over the cap, a viewer's resolve returns `{"status": "deferred", "retry_after": s}` and writes
     nothing. Author jobs are never capped: the author owns its own budget.
8. **The runner.** `python -m patternbuffer.service --world PATH --world-id ID [--view-frame F]
   [--no-author] [--port N]` serves sessions over **localhost HTTP + JSON**, using only the standard
   library:
   - `POST /call {session, verb, args}`;
   - `GET /now`;
   - `GET /changes?since=` (S2).

   It binds 127.0.0.1 only. Wider hosting (a phone, the public site) is Kabe's call and is not built
   here. With no model callable configured, the runner refuses model-routed resolves (`status:
   "no_model"`); code routes still answer if a `--generator MODULE:FN` is given.

## What does not change

- No engine verb, row shape or read answer changes.
- A host that never constructs a `WorldService` sees nothing new.
- MCP-WRAPPER-V1's server is untouched. Its registry and `dispatch` are reused, not copied.

## Not in scope

- **S2:** the view export and the `changes(since)` feed for offline mirrors.
- **E3.**
- **The transport to phones** and **holo-bridge** (Kabe's).
- **Multi-world hosting:** one service, one world (the 1:1 invariant).

## Questions for construct, before pbr

1. Is `run(fn)`, with one closure per turn, a workable migration from your direct porcelain calls?
   Or would you rather host the service on **your** thread (`svc.attach(world)` plus `svc.pump()`
   from your loop)?
2. The `perceptible` hook: you already decide scene visibility for `furnish_scene`. Can that
   function be passed as-is?
3. Mirroring a viewer's resolve into the player's view copies `furnish_scene`: the gate's default
   status (`stated`), in the view frame. Should a perception mirror be `observed` instead? That is
   more honest about provenance, but it would differ from your existing furnished rows.

## Checks (for the build)

1. Every job runs on the owner thread, so one connection writes.
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
