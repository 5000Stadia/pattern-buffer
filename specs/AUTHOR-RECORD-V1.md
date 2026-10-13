# AUTHOR-RECORD-V1: an author session that writes canon, never the player's view

**Status:** r1, for pbr review and for Photonic's review as the host that needs it. Author: pb,
2026-10-13.
**Source:** roadmap R45. Photonic's SEAM (a) (m019da7): "Photonic records where people stand, sit
and are heading, mostly out of the player's sight. That has to be canon-only (or another frame),
never the player's view." Kabe said yes on gate gf985f8 ("2 agree", given in Photonic's console and
relayed in ma3a689).
**Builds on:** WORLD-SERVICE-V1 (sessions, roles, the owner-job queue, the runner), VIEW-EXPORT-V1
§5 (the recorder's bare `recorded` / `refused` answer, `last_record_outcome`), FRAME-CONTINUITY-V1
(`frame_scope`, `_scoped_frames`).

## Need

The service has two roles today:
- a **viewer** reads the player's view;
- a **recorder** writes play events. Each item goes in twice, to canon and to the view frame, as
  `observed`, because the player saw it happen.

Photonic writes something else. Where a person stands, sits, and is heading is the world's truth,
whether or not the player sees it. Those rows belong in canon (or in one character's knowledge)
and **must not** reach the player's view frame. A recorder can't do this: every recorder write is
also a view write. Photonic writes rarely: arrivals, room crossings, sitting and standing, and a
final "no way". It never stores motion.

## The shape

A third role, **author**:

```python
service.session("photonic", role="author")
session.call("record", items=[...], at=None, frame="canon")   # -> {"status": "recorded"} | {"status": "refused"}
```

### 1. Who may open one

- `WorldService.session(name, role="author")` is allowed in **both** modes:
  - **Standalone runner** (a world with no author): the runner gains `--author NAME`, repeatable,
    like `--recorder`. A name given as both is refused at start (`ValueError`).
  - **Under a host author** (construct): only the host can call `session(...)`, so opening an author
    session is the host's own decision to let a module write canon. The recorder stays
    standalone-only, because play events go to the host author. An author session is not a play
    event, so that reason doesn't apply.
- An author session holds every viewer verb, unchanged: it reads the player's view, never canon.
  Writing canon gives it no canon reads. A canon read surface is a separate decision, not made here.

### 2. `record` for an author

`record(items, at=None, frame="canon")`:

- **`frame`**: `"canon"` (the default), or one `knows:<observer>` frame **outside the player's
  view**:
  - The view's frames are `_scoped_frames(view_frame, frame_scope, head)`: the view frame itself,
    plus what the host's `frame_scope` adds (continued frames, merged observers), as of the log
    head when the job runs on the owner thread.
  - A frame in that set is refused. The player's view is written by play (the recorder) or by
    `resolve`, never by the author.
  - Any other frame name (`plot:*`, `scene:*`, an empty or non-string name) is refused in V1.
    Canon and characters' knowledge are what Photonic named.
- **`items`**: the recorder's item rules apply unchanged (`_clean_items`):
  - only `_RECORD_KEYS` (`entity`, `attribute`, `value`, `value_type`, `valid_from`, `valid_to`,
    `timeless`);
  - no item-level `frame` or `status`;
  - no bookkeeping subject (`a:`, `attr:`) and no barred attribute (mechanism, semantics, canon
    identity edges, meta);
  - `value_type` in `entity` / `literal` / `delta`.
- **No handles.** An author names canonical ids. A handle-shaped `entity`, or an entity `value`
  that is a handle, refuses the batch (`invalid`). Handles are the player's device's ids for unseen
  things, and an author never needs them.
- **Status `stated`.** The author states the world's truth; nobody observed it. Every row goes
  through `commit_set(..., classify="rules")`, so the ingestor writes it, as the role-authority
  matrix requires.
- **One frame per call.** Each item is written **once**, into `frame`. Unlike the recorder, nothing
  goes into canon *and* a view.
- **`at`**: as the recorder. An item with no `valid_from` and not `timeless` gets `at`, or
  `service.now()`.
- **Atomic**: one `commit_set` per call. Any refusal writes nothing.

### 3. The answer

- The same bare answer as the recorder (VIEW-EXPORT-V1 §5 r3): `{"status": "recorded"}` or
  `{"status": "refused"}`, nothing else.
  - The full outcome (receipt, or cause and reason) goes to `last_record_outcome` and the log
    (`INFO` for a commit, `WARNING` for a refusal), as for the recorder.
  - **Why bare for a trusted writer:** Photonic's author runs on the player's device, so its answer
    reaches the device. One wire shape for every write keeps that simple.
- A wrong `frame` is refused the same way, with the reason kept for the host.

### 4. What changes for the reads

Nothing in the read path changes.
- An author's canon write never enters `known`, because `known` is the view frame under its scope.
- It can change the present layer (VIEW-EXPORT-V1 §2) when it moves a thing into a covered place,
  and it can change R46's people layer. Both are canon reads by design.
- The next feed answers whatever changed. A write to canon alone gives no `known` op.

### 5. Under a host author

When construct hosts and opens an author session for a module, construct's own writes and the
author's are both owner-thread jobs on one World, so there is no new concurrency. Construct sees
the author's rows in its log like any other canon rows. Whether construct opens such a session is
construct's call, not this spec's.

## Prior art

None needed. This narrows the existing recorder: one frame instead of two, `stated` instead of
`observed`, and the view excluded instead of required.

## Not in this spec

- A canon read surface for authors.
- Writing any frame other than canon and characters' `knows:` frames.
- A JS client for author writes. R47's queued `record` covers it: the queue names its role's verb.
- Motion. Photonic stores facts at rest.

## Tests (the build's acceptance)

1. **Canon only.** An author `record` with no `frame` writes each item once into canon, `stated`.
   The view frame gains no row. The next `feed` from the prior cursor has no `known` op.
2. **A character's knowledge.** `frame="knows:person:bram"` (not the view) writes there only.
3. **The view refused, under each scope.** These are all refused with nothing written:
   - `frame` equal to the view frame;
   - a frame the host's `frame_scope="continued"` adds (a declared `frame_continues_as` source);
   - a frame `"merged"` adds (a `same_as` member's `knows:` frame).
4. **Other frames refused.** `plot:x`, `scene:y`, `""` and `42` are refused.
5. **Item rules.** An item-level `frame` or `status`, an extra key, a barred attribute, an
   `attr:` subject, and a handle as `entity` or as an entity `value` are each refused, writing
   nothing.
6. **Atomic.** A batch with one bad item writes nothing.
7. **Bare answer.** A commit answers exactly `{"status": "recorded"}`; every refusal answers exactly
   `{"status": "refused"}`. `last_record_outcome` holds the receipt or the cause and reason.
8. **Roles.**
   - A viewer's `record` is refused.
   - A recorder's `record` is unchanged: canon and view, `observed`, and it refuses `frame`.
   - `session(role="author")` works on a hosted (non-standalone) service, where `role="recorder"`
     stays refused.
   - An author holds every viewer verb, and its reads are the view's.
9. **Runner.**
   - `--author photonic` makes that session an author over `POST /call`.
   - A name given to both `--author` and `--recorder` fails at start.
   - The HTTP answer for a commit is byte-identical to the recorder's.
10. **Mirror.** An author moves a thing into a known drawer in canon. The next feed answers a
    `put present` for it and no `known` op.
11. **Full suite green.** The MCP tool count is unchanged (45): the author verb is a service verb,
    not a porcelain one.

## Lexicon (added with the build)

- **author session**: a service session whose `record` writes canon, or one character's `knows:`
  frame outside the player's view, as `stated`. Contrast **recorder**: play events, written to
  canon and the view frame as `observed`.
