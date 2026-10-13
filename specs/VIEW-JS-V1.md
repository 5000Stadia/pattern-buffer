# VIEW-JS-V1: a small `patternbuffer` JS module for the browser

**Status:** r2.1 (pbr's code review: a queued timed item must carry its own time). r2. r1.1 took holo-emitter's review (m47f6b9: eviction, cross-tab locks, apply off the frame loop). r2 answers pbr's r1.1 RED (a viewer session for `sync`; queues namespaced by world; the queue's role and `onRefused` are parameters) and drops `queue.lost` (see §3). For pbr review and for Photonic's and holo-emitter's review as the two clients.
Author: pb, 2026-10-13.
**Source:** roadmap R47. Photonic m019da7: "By Kabe's rule (each element used from its home
project), the JS store is yours: your contract, your vectors, your spec. Will you own a small
patternbuffer JS module (view/1 apply against the vectors, plus a queued record)?" holo-emitter
mb70060: "The browser holds and applies your answers and never computes them. It's seeded from the
static export and checked against view-feed-v1.json. Photonic's on-device writes stay a pending
overlay, sent through 'record' once a service exists." Kabe said yes on gate gf985f8.
**Builds on:** VIEW-EXPORT-V1 (§3 `apply` is the contract, §7 what a client must not assume),
VIEW-PEOPLE-V1 (the people layer), AUTHOR-RECORD-V1 and the recorder (the two `record` doors).
**Input:** Photonic's in-browser stand-in, offered as a starting point (m019da7; asked for in
m27078b). It will be read, and what is adopted from it noted, before the build.

## Need

The game and the manor run in Safari as static pages. pattern-buffer is Python. Both neighbours
agreed the browser holds the answers our engine gives and **never works them out itself**. Today
each of them would write its own `apply`. By Kabe's rule (g1eeae0) that code belongs here, with the
contract and its vectors, so a contract change and its client change land together and fail
together.

## The shape

ES modules under `js/patternbuffer/`, with no dependencies and no build step. Safari imports them
as they are.

```
js/patternbuffer/view.mjs     apply(document, answer) -> document    (pure; VIEW-EXPORT-V1 §3, VIEW-PEOPLE-V1 §3)
js/patternbuffer/store.mjs    openView({backend, worldId, viewFrame, session, seed}) -> View
js/patternbuffer/queue.mjs    openQueue({backend, worldId, session, role, onRefused}) -> Queue
js/patternbuffer/idb.mjs      idbBackend(dbName) -> Backend           (IndexedDB; the browser's backend)
js/patternbuffer/index.mjs    re-exports
js/test/*.test.mjs            node --test
```

### 1. `apply` (view.mjs)

- `apply` is a line-for-line port of `patternbuffer.mirror.apply`, people layer included:
  - the same ops (`clear`, `reveal`, `del`, `put`);
  - the same order;
  - the same errors, which `apply` throws as `Error` with the Python message text.
- **It is pure.** It returns a new document and never mutates its input. It uses
  `structuredClone`, available in Safari 15.4+ and node 17+.
- *(r1.1, holo-emitter 3)* **`apply` is not for every frame.** It clones the whole document for
  each answer. Call `sync` when the game wants fresh state (on arrival, on a timer of seconds,
  after a flush), never from a render loop.
- **Equality is structural.**
  - Documents compare as JSON values: object key order is free, as the vectors' `about` already
    says.
  - JS cannot tell `1220.0` from `1220`. No client computes a digest or a cursor, so nothing
    depends on that difference.
  - The module exports `sameDocument(a, b)` (a deep JSON equality), which the tests use.
- **The device never folds.** There is no `state`, no fold and no identity in JS. The module
  answers reads only from what the document holds:
  - `known(doc, id)`;
  - `present(doc)`;
  - `people(doc)`.

  These are thin accessors that return `undefined` for an absent subject. Per VIEW-EXPORT-V1 §7,
  absent means unknown to the player, never "doesn't exist".

### 2. The persisted view (store.mjs)

`openView({backend, worldId, viewFrame, session, seed})`:

- *(r2, pbr P1)* `session` is the runner session name the view's `feed` calls use. Any role can
  read the view. Every `feed` request is the body
  `{"session": session, "verb": "feed", "args": {"since": cursor}}`. `since` is omitted when the
  cursor is `null`.

- **Loading.** It loads the persisted document for `(worldId, viewFrame)`. If there is none, it
  starts from `seed`: the static `view.json` the page ships (VIEW-EXPORT-V1 §6), or the empty
  document.
- **`view.doc`** is the current document.
- **`view.sync(transport)`**:
  1. calls `feed` with `since = doc.cursor`;
  2. applies the answer;
  3. persists, then replaces `view.doc`.

  If `apply` throws, the document is unchanged and `sync` rejects. A later `sync` with the same
  cursor then gets a reset from the server, because a cursor the server can't diff from is
  answered with `clear`.
- **`view.replace(document)`** persists a fresh export, for a page that downloads a new
  `view.json`.
- **Writes are serialized across tabs** *(r1.1, holo-emitter 2)*.
  - `sync` and `replace` run inside `navigator.locks.request(key, ...)`, where `key` is the view's
    backend key (§4). The lock exists in Safari 15.4+, the same floor as `structuredClone`.
  - Inside the lock, `sync` re-reads the persisted document before calling `feed`. Two tabs on one
    world (the lab and the manor) therefore sync one after the other, and the second carries on
    from the first's cursor instead of overwriting it.
  - Where `navigator.locks` is absent (node, old browsers), a per-object promise chain serializes
    the calls instead.
  - One document per page is still the agreed shape (holo-emitter, m019da7).
- **A fresh start is reported** *(r1.1, holo-emitter 1)*. `view.reseeded` is `true` when
  `openView` found no persisted document and started from `seed`. That covers a first visit, and
  Safari evicting script-written storage after seven days without a visit. The view itself
  recovers: the seed loads, and its stale cursor gets a `clear`.

### 3. The queued record (queue.mjs)

Photonic's on-device writes wait in a queue until a service is reachable.

- `openQueue({backend, worldId, session, role, onRefused})` gives a persisted FIFO of calls
  `{verb: "record", args}` *(r2, pbr P1 ×2)*:
  - `worldId` namespaces the queue's key and lock, so two worlds using the same session name (say,
    `author`) never share a queue.
  - `session` is the name the runner knows as a recorder or an author; every flushed body names
    it.
  - `role` is `"recorder"` or `"author"`, as the host configured that session. It is required, and
    any other value throws.
  - `onRefused(call)` is an optional callback. Without one, a refused call is dropped and logged
    with `console.warn`.
- `queue.add(items, {at, frame})`:
  - validates the shape locally against the recorder's key rules (`_RECORD_KEYS`, no item
    `frame`/`status`), so a malformed call fails at once rather than at flush;
  - `frame` is passed only when given. With `role: "recorder"`, `add` throws when `frame` is
    given, because the recorder refuses it. With `role: "author"`, a `frame` other than `"canon"`
    or `"knows:"` followed by a whole id (the engine's `ID_RE`) throws. The server checks again;
    the local check only fails early;
  - then persists the call.
- `queue.flush(transport)` sends calls in order, one at a time:
  - `{"status": "recorded"}` → the call is dropped;
  - `{"status": "refused"}` → the call is dropped and reported through `onRefused(call)`. A
    refusal is final; the reason stays with the host (VIEW-EXPORT-V1 §5).
  - a transport failure, or a 5xx or 504 → the flush stops, keeping this call and everything after
    it, and resolves with how many it sent. The next flush resumes.
  - a 400 → handled as refused, because the server read the call and declined it.
- **Eviction** *(r1.1, holo-emitter 1; r2)*.
  - Safari can evict IndexedDB after seven days without a visit, unless the site is on the home
    screen. That would lose pending calls silently.
  - `openQueue` and `openView` call `navigator.storage.persist()` where it exists, and expose the
    outcome as `.persisted` (`true`, `false`, or `null` when the API is absent). That is the
    defence.
  - Detection is limited to `view.reseeded`. Eviction clears the whole origin, every marker
    included, so after it the module cannot tell eviction from a first visit. r1.1's `queue.lost`
    marker could never fire in the case it was for, so r2 drops it. The game, which knows whether
    the player has been here before, decides what to say.
- `flush` runs inside `navigator.locks.request(<the queue's key>, ...)` (or the promise-chain
  fallback), so two tabs never send the same call twice.
- `queue.pending()` lists the waiting calls, so the game can draw its own overlay. **The queue
  never applies its calls to the document.** The document holds only the server's answers;
  the overlay is the game's.
- *(r2.1, pbr)* **Every queued timed item carries its own time.**
  - A non-timeless item with no `valid_from`, given without a call-wide `at`, is refused by `add`.
    That includes an item with only `valid_to`.
  - Otherwise the server stamps it with its own `now()` at each delivery. After a lost answer, the
    retry would then write a different, later fact, or turn an interval into a refusal.
  - With the time in the persisted call, a retry is byte-identical, and two deliveries read exactly
    as one.
  - The game supplies the time from its own world clock. Photonic already sets `valid_from` at the
    event's world time. The module never reads a client clock.
- **Delivery is at least once.** A call whose answer was lost in transit is sent again on the
  next flush. A fact at rest written twice folds to the same answer. A `delta` value (an accrual)
  written twice would count twice, so **`add` refuses an item with `value_type: "delta"`** in V1.
  An idempotency key on `record` is the fix if one is ever needed; it is not added here.

### 4. Transport and backend

- **`transport`** is `async (body) => {status, json}` for `POST /call` with
  `{session, verb, args}`. `httpTransport(baseUrl)` wraps `fetch` with
  `Content-Type: application/json`.
- **Today's runner limits.** It serves loopback hosts only and grants no cross-origin requests
  (WORLD-SERVICE-V1). So a page served from elsewhere can't reach it, and the queue simply waits.
  Hosting a service the phone can reach is Kabe's decision, still open (holo-emitter's point B).
  The module adds no server.
- **`backend`** is `{get(key), put(key, value), del(key)}`, async.
  - `idbBackend(dbName)` is IndexedDB: one object store, structured-cloned values.
  - `memoryBackend()` is for tests.
  - Keys *(r2, pbr P1)*. Every part is `encodeURIComponent`-encoded, so a `:` inside a world id
    or frame name can't make two keys collide:
    - `pb:view:<worldId>:<viewFrame>` for a document;
    - `pb:queue:<worldId>:<session>` for a queue, holding the whole array, rewritten on each
      change. Writes are rare.

    The lock names are the same strings.

### 5. Ownership and drift

- Python's `mirror.apply` stays the reference. When the two disagree, the vectors decide.
- `tests/test_js_module.py` runs `node --test js/test` when `node` (≥ 18) is on the path, so the
  Python suite fails when the JS drifts from the vectors. It is skipped, with the reason given,
  when node is absent.
- A contract change to VIEW-EXPORT-V1 or VIEW-PEOPLE-V1 regenerates the vectors and fails the JS
  test until the port follows.
- holo-emitter and Photonic import from this repo's `js/patternbuffer/`, copied or vendored at a
  tagged commit. How they vendor it is theirs.

## Prior art

- **Adopted: Replicache's client shape.** One persisted document, a pull that applies a patch, and
  a pending-mutation queue sent in order, with the local view never mutated by pending writes.
  Ours differs in one way: the queue's writes don't rebase over the document. The game's overlay
  does that work, because only the game knows how to draw a pending write.
- **Rejected: a client-side engine port.** VIEW-EXPORT-V1 rules it out, and both neighbours
  agreed.
- **Rejected: a dependency such as `idb`.** The IndexedDB use is about 40 lines; a dependency would
  need a build step or a CDN.

## Not in this spec

- Serving the module (a CDN or npm). Vendoring is the clients'.
- A server the phone can reach (Kabe's).
- Rendering, overlays and the game's use of `pending()`.
- Any change to the Python contract. A mismatch found while porting goes to the vectors and the
  spec, through pbr, before the JS works around it.

## Tests (the build's acceptance)

1. **Vectors.**
   - `node --test` replays every sequence in `tests/vectors/view-feed-v1.json` and
     `tests/vectors/view-feed-people-v1.json` (R46): start, apply each answer, and compare to
     `expect` with `sameDocument` after every step.
   - Every error case the Python `apply` raises is thrown, with its message.
2. **Purity.** `apply` leaves its input deep-equal to before.
3. **Store.**
   - A view opens from its seed, syncs through a fake transport, persists, and reopens to the
     same document.
   - *(r2)* The fake transport asserts each body: `{"session": s, "verb": "feed", "args":
     {"since": c}}`, with `since` absent on a null cursor.
   - A throwing `apply` leaves the persisted document unchanged.
   - Two concurrent `sync` calls run one after the other.
3a. *(r1.1)* **Cross-tab and fresh start.**
   - With a fake `navigator.locks`, two views on one backend key run `sync` one after the other,
     and the second feeds from the first's cursor.
   - `reseeded` is `true` on a first open and `false` on a reopen.
4. **Queue.**
   - Calls flush in order.
   - `recorded` drops a call; `refused` and a 400 drop it and call `onRefused`.
   - A transport error or a 5xx stops the flush and keeps the rest, and a reopened queue still
     holds them.
   - `add` refuses a `delta` item, an item `frame`, and an unknown key.
   - *(r2.1)* `add` refuses a timed item with no `valid_from` and no `at`, including the interval
     case (`valid_to` only). After a lost answer, the retry's body is byte-identical to the first.
   - *(r2.1)* End to end: the same author call (open, and an interval) delivered once and twice
     gives exports equal in everything but the cursor, and equal `state` inside and after the
     interval.
   - *(r1.1)* `persisted` reflects a fake `navigator.storage.persist()`, or is `null` without one.
   - *(r2, pbr P1)* Two worlds with one session name on one backend keep separate queues and
     locks, and each flush sends only its own world's calls. A world id containing `:` doesn't
     collide.
   - *(r2, pbr P1)* With `role: "recorder"`, `add` with a `frame` throws. With `role: "author"`,
     `frame: "knows:person:bram"` is accepted and sent in `args`, while `frame: "knows:"` and
     `frame: "plot:x"` throw. A missing or unknown `role` throws at `openQueue`.
   - `onRefused` receives the refused call. Without it, a `console.warn` is recorded.
   - Two flushes under a fake lock never send one call twice.
5. **End to end** (Python test, node present): a `Runner` on a fixture world with an author
   session.
   - The JS view syncs over `httpTransport` to the runner, and its document equals the Python
     `export`.
   - A queued author `record` flushes, and the next sync shows its effect in the present or
     people layer.
6. **IndexedDB.** `idbBackend` follows the backend contract. It runs in node only if a global
   `indexedDB` exists, and is otherwise skipped with the reason given. Photonic's Safari check is
   the real test, reported back as a SEAM ticket if it fails.
7. **Drift guard.** `tests/test_js_module.py` passes in the full suite, or skips with the reason
   when node is missing.

## Lexicon (added with the build)

- **view module**: the `js/patternbuffer/` ES modules: the browser port of `mirror.apply`, a
  persisted view, and a queued `record`. It never folds.
