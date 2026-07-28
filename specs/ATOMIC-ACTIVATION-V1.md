# ATOMIC-ACTIVATION-V1 — all-or-none visibility for a multi-row set — r11

**Status:** r11 DRAFT → pbr (re-review after r10). r10 re-review (`<caebdfae…>`):
**F2–F8 GREEN, F1 YELLOW** — provenance, phase matching, entry (F1.a), and the
terminal `try/finally` are ALL accepted; one symmetric lifecycle boundary
remains: the authorizer is installed but never **removed/restored**, so a later
non-atomic INSERT hits the lingering `phase=none` callback and fails; and
rollback-unconfirmable must **fail closed** (poison the connection) rather than
hand back a reusable facade over a possibly-partial transaction. r11 pins the
**complete outer unit lifecycle** — balanced install/restore plus every failure
branch (§B1). pbr: "provenance, phase matching, entry, and terminal try/finally
are accepted."

**(r8 status, for lineage)** r7 re-review (`<eaf77b9f…>`): pbr *probed live* and
falsified r7's premise:
Python `Connection.commit()`/`rollback()` DO compile transaction-control SQL,
so the authorizer sees them as `SQLITE_TRANSACTION` too (`con.commit()` →
`not authorized; callback (22, COMMIT)`); there is NO C-API that bypasses
compilation. A total-deny authorizer blocks the owner's own finalize; allowing
`SQLITE_TRANSACTION` re-opens `execute("COMMIT")`. r8 replaces the false "clean
separate channel" with a **provenance-gated authorizer** — an unforgeable
private owner-finalize flag consulted by the callback, enabled only
synchronously around the single raw terminal commit/rollback (§B1); the seven
GREEN findings stay frozen. Ruling delivered to the first host 2026-07-13
(pb `<54152f82…>`): engine-side; the host staging-world copy is REJECTED not
because a duplicate `world_id` is categorically forbidden (whitepaper A5 permits
independent never-rejoined forks to share one) but because a copy-then-swap is
**not one atomic log transition for the live instance** and breaks
continuity/rejoin. The ADOPTION-set gap is closed by the typed operation set
(§C). Gates the host's WORLD-GROWTH G1 slice; after GREEN the host routes the
consumed-contract delta to cr.
**Kind:** one ingest mode (`atomic=True`, model-free classify only) + one
porcelain verb (`commit_set`) + a **deny-by-default database capability facade**
with a **provenance-gated unit-scoped SQLite authorizer** owning the buffer's
unit-of-work (only PB's DML/read exposed; transaction-control/schema/attach/
pragma SQL denied for borrowed execution; an operation-specific owner phase alone
authorizes the BEGIN and the single terminal commit/rollback) + an explicit
snapshot/restore abort contract + a shared-path `retract` target-validation
repair. No schema change, no new log vocabulary, no visibility indirection, no
fold change. Default-path behavior byte-identical.

## Review response (r10 → r11)

| finding | r10 pin (pbr, verified live) | r11 resolution |
|---|---|---|
| **F1** YELLOW | (exit) the unit-scoped authorizer is installed but never removed/restored — after a unit the next ordinary non-atomic INSERT's implicit BEGIN hits the lingering `phase=none` callback and fails `not authorized`; (fail-closed) rollback-unconfirmable must not uninstall + return a reusable facade while a partial transaction may remain | (§B1 outer lifecycle) the owner installs the authorizer on unit-enter (saving any prior) and **restores/removes it in an OUTER `try/finally`** on every exit — commit success, confirmed rollback, or BEGIN failure — so the connection returns to its exact pre-unit state and later non-atomic work is unaffected. **Rollback-unconfirmable fails closed:** the owner **poisons/closes the connection** (every later op raises) and propagates the raw error (F6) — no reusable facade over uncertain state. Oracle 10 proves same-connection non-atomic work resumes after both success and confirmed abort; oracle 14 proves no borrowed op can finalize after a poisoned rollback. |

Frozen GREEN + accepted (r10): **F2–F8**, and F1's provenance architecture,
operation-specific phase, entry (F1.a), and terminal `try/finally` (F1.b) — r11
adds only the outer install/restore balance and the fail-closed poison branch.

### Prior round (r9 → r10)

| finding | r9 pin (pbr, verified live) | r10 resolution |
|---|---|---|
| **F1** YELLOW (F1.a only) | r9's manual-`isolation_level` entry is not default-path-neutral: `isolation_level=None` is statement-level autocommit, so globally changing the sole connection makes existing non-atomic multi-statement writers (classifier `_store`: INSERT-OR-REPLACE → UPDATE version → commit) independently durable/visible with a no-op final commit — contradicting the frozen byte-identical/default-path pin | (§B1 entry) **no isolation-level change.** Preserve the connection's existing transaction config; install the authorizer; issue the explicit owner `BEGIN` on the raw connection under `phase=begin` (`try/finally`). Because a transaction is then already open, the first PB DML does NOT trigger an implicit BEGIN, and borrowed BEGIN stays denied at `phase=none`. Oracle 14/default-path extended to assert the preexisting isolation config is unchanged AND the non-atomic sidecar statement-grouping is unchanged. |

Frozen GREEN + accepted (r9): **F2–F8**, and F1's provenance architecture +
operation-specific phase + `try/finally` teardown (F1.b) — r10 corrects only the
F1.a entry mechanism to be default-path-neutral.

### Prior round (r8 → r9)

| finding | r8 pin (pbr, verified live) | r9 resolution |
|---|---|---|
| **F1** YELLOW | (a) transaction ENTRY unspecified: `SQLITE_TRANSACTION` also covers BEGIN, and the deny-authorizer blocks the implicit BEGIN the first DML triggers (pbr: first INSERT → `not authorized … BEGIN`); (b) teardown not exception-safe: if the raw commit/rollback raises while the flag is still true, later borrowed transaction SQL inherits authorization | (§B1) the flag becomes an **operation-specific private phase** `{none, begin, commit, rollback}`; the authorizer allows `SQLITE_TRANSACTION` ONLY when the phase equals the operation being compiled. The owner controls BEGIN explicitly (manual `isolation_level`, so no implicit borrowed BEGIN reaches SQLite mid-unit) under `phase=begin`; each phase is set synchronously around exactly its raw call and **reset to `none` in `try/finally`**, so a raised commit/rollback (incl. the rollback-unconfirmable case) never leaves the capability authorizing. Oracle 14 proves owner BEGIN + first PB DML succeed while borrowed BEGIN stays denied, and a terminal-call failure leaves the phase `none` (subsequent `execute("COMMIT")` denied). |

Frozen GREEN (r8): **F2–F8** unchanged; the provenance design, allowlist,
cursor/property closures, and borrowed SQL-class denials all stand — r9 only
makes the owner phase operation-specific, entry-safe, and exception-safe.

### Prior round (r7 → r8)

| finding | r7 defect (pbr, verified live) | r8 resolution |
|---|---|---|
| **F1** RED | r7's premise was FALSE: `Connection.commit()`/`rollback()` compile `SQLITE_TRANSACTION` and ARE seen by the authorizer (`con.commit()` → `not authorized (22, COMMIT)`); no C-API bypass exists. Total-deny blocks the owner's finalize; allowing `SQLITE_TRANSACTION` re-opens `execute("COMMIT")`. The "clean separate channel" does not exist. | **provenance-gated authorizer** (§B1): the callback denies `SQLITE_TRANSACTION`/`SAVEPOINT`/etc. for borrowed execution, but consults an **unforgeable private `_owner_finalizing` flag** (not reachable through the facade) that the owner sets **synchronously** around its single raw terminal `commit()`/`rollback()` and clears immediately — no borrowed/reentrant execution is possible in that window (single-writer, synchronous). The spec no longer claims `commit()`/`rollback()` compile no SQL. Oracle 14 proves borrowed COMMIT/ROLLBACK/END stay denied, owner commit + exception rollback succeed, second-connection stays all-or-none. |

Frozen GREEN (r7): **F2–F8** unchanged; the facade's allowlist, cursor/property
closures, and SQL-class denials for borrowed execution all still stand — r8
changes only how the OWNER's terminal finalize is authorized.

### Prior round (r6 → r7)

| finding | r6 defect (pbr, verified live) | r7 resolution |
|---|---|---|
| **F1** RED | the facade shape is right, but one ambient boundary survives inside an ALLOWED method: SQLite accepts transaction control as ordinary SQL, so `facade.execute("COMMIT")` / `facade.cursor().execute("ROLLBACK")` during a unit bypasses `commit()` ownership with no raw handle (same channel: `BEGIN`/`END`, `SAVEPOINT`/`RELEASE`/`ROLLBACK TO`, `ATTACH`/`DETACH`, txn-changing `PRAGMA`, `VACUUM`, DDL). r6 rejects `executescript`/DDL but does not gate transaction-control SQL through `execute`. | **unit-scoped SQLite authorizer** (§B1): during a unit the owner installs `set_authorizer` denying `SQLITE_TRANSACTION`/`SAVEPOINT`/`ATTACH`/`DETACH`/mutating-`PRAGMA`/DDL/`VACUUM` opcodes at COMPILE time for borrowed execution, allowing only PB's DML/read classes; `facade.execute("COMMIT")` raises before SQLite acts. The owner finalizes via the C-API `commit()`/`rollback()` (no SQL compiled → the authorizer never sees them). A string classifier is rejected as porous (comments/`WITH`). Oracle 14 gains the SQL-class denials. |

Frozen GREEN (r6): **F2** (model-free boundary), **F3** (committed-id retract
snapshot), **F4** (snapshot/restore), **F5** (shared-path validation), **F6**
(taxonomy/types/import/rollback-unconfirmable), **F7** (non-idempotence+probe),
**F8** (inline-default fidelity, `commit_set` `rules` default, parsed MCP error).
The facade's handle/property/cursor closures (r6) also stand.

### Prior round (r5 → r6)

| finding | r5 defect (pbr, verified live) | r6 resolution |
|---|---|---|
| **F1** RED | r5 stayed *enumerated forwarding*; Python 3.12 exposed `executescript`-returns-cursor, cursor-self-return, `autocommit=True` cross-connection visibility, `close()` | **deny-by-default capability facade** (§B1): allowlist only; cursor proxies self-return; `.connection` is the facade; `autocommit`/`isolation_level` setters + `close()` owner-only; private terminal path; deny-by-default assertion. |

### Prior round (r4 → r5)

| finding | r4 defect (pbr, verified live) | r5 resolution |

| finding | r4 defect (pbr, verified live) | r5 resolution |
|---|---|---|
| **F1** RED | the stable proxy leaks the raw connection TRANSITIVELY: `Connection.execute()`/`cursor()` return a native `Cursor` whose `.connection` is the raw `Connection`, and `Connection.__enter__()` returns the raw connection — a holder caches `proxy.execute(...).connection` pre-BEGIN and bypasses the gate. Separately, a blanket create-once salience guard breaks `test_salience_rebuild_parity` (drops `sidecar_salience`, expects `rebuild()` to recreate). | **cursor proxy + context closure** (§B1): every `execute`/`cursor` path returns a WRAPPED cursor whose `.connection` is the proxy (or unavailable); `proxy.__enter__` returns the proxy; `__exit__`/commit/rollback/`isolation_level`/`executescript` all route through the unit owner. Salience: `salience()` reads stay DDL-free (create-once), but `rebuild()` keeps an explicit recreate path (allowed OUTSIDE a unit, rejected during). Oracle 14 extended to cache through `execute().connection`, `cursor().connection`, and `__enter__` pre-BEGIN. |
| **F3** YELLOW | B3 and C1 contradict: B3 says a retract targets an assertion present at call time (never one minted earlier in the set), but C1's "log or staged prefix" re-enables guessed `a:<seq>` targeting of a staged assert | **retract target eligibility = the pre-call committed-id snapshot** (§C1) — staged-prefix visibility stays valid for cycle/ancestry/recency, NOT for retract targets; standalone retract validates against its call-time log. Negative oracle: assert then retract a guessed new id → `exception` abort. |
| **F6** YELLOW | B2 STILL lists authority/semantics as skips whose receipts ride `AtomicAbort` — contradicting B6 (they are exceptions); field TYPES unfrozen; `AtomicAbort` import location + rollback-unconfirmable surface unstated | (§B2/§B6) authority/semantics removed from the B2 skip parenthetical; field types frozen (`skipped`: list of `{entity, attribute, value, reason}`; `gate_skip`→`error=null`; `exception`→`skipped=[], error={type,message}`); public import location named; a rollback-unconfirmable outcome is explicitly NOT `AtomicAbort`. |
| **F8** YELLOW | the sugar default contradicts source: `ingest_structured` defaults `classify="inline"` (ingest.py:310), so `atomic=True` cannot "share `classify=rules`"; MCP error envelope byte-shape unspecified | (§C5/§D) `ingest_structured` keeps `classify="inline"`; under `atomic=True` an omitted/`inline`/`batch` classify raises `ValueError` (caller passes `rules`/`defer` explicitly); `commit_set` (new verb) defaults `classify="rules"`. MCP abort returns a pinned `isError:true` + `structuredContent:{cause,skipped,error}` envelope with an exact wire fixture. |

Frozen GREEN (r4): **F2** (model-free boundary), **F4** (snapshot/restore +
cursor-snapshot/`last_skipped` pins), **F5** (shared-path target validation,
subject to the F3 pre-call boundary), **F7** (non-idempotence + probe).

### Prior round (r3 → r4)

| finding | r3 defect (pbr, verified live) | r4 resolution |
|---|---|---|
| **F1** RED | `.commit()`/`.rollback()` gating does not own EVERY boundary: `sqlite3.executescript()` implicitly commits before running, and salience `_ensure_schema()` calls it on normal access (salience.py:56, invoked at :53/:65/:79) — pbr reproduced a rollback failing to remove a row after an intervening `executescript`. Also a holder that cached the real connection pre-BEGIN bypasses a while-open-only gating view. | **structural ownership** (§B1): the buffer exposes ONLY a stable proxy at ALL times (raw connection never handed out, so nothing can cache it), routing its own commits through it too; the proxy owns commit/rollback AND implicit-commit ops (`executescript`, isolation-level DDL). Sidecar schema-ensure moves to **one-time init** (create-once guard, not per-access); the proxy rejects `executescript` while a unit is open. The salience-ensure-schema path is added to the second-connection oracle. |
| **F3** YELLOW | "retract-of-staged" is not expressible — asserts get auto-assigned `a:<seq>` ids during execution, but a retract op needs a concrete `assertion_id` before execution; predicting head offsets is not a public contract and breaks when an assert emits meta-rows | **removed** (§B3, oracle 4). Recency-within-set is the sole ordering contract (it already proves order). A symbolic op-result reference vocabulary is V-next, only if a measured case forces it — no offset-prediction contract ships. |
| **F4** GREEN | (snapshot/restore is right) | pins folded (§B4): snapshot the prior cursor BEFORE porcelain applies `at=`; restore the object's prior `last_skipped` while THIS abort's skips ride `AtomicAbort` — one exact meaning for "restore" + "diagnostics preserved". |
| **F6** YELLOW | taxonomy risk: authority/semantics conflicts currently RAISE, not skip — silently converting them to `gate_skip` would break the byte-identical non-atomic path; `AtomicAbort` timing vs COMMIT undefined; payload fields loose | (§B6) `gate_skip` covers ONLY the ops that skip on the non-atomic path (malformed id, cycle, self-edge); authority + semantics RAISE → `cause=exception` carrying the original error (never reclassified). `AtomicAbort` is emitted ONLY after rollback is confirmed; a fault after COMMIT is NOT an abort (it is the F7 ambiguous outcome). Exact payload: `{cause, skipped, error}`. |
| **F8** YELLOW | contract unfinished: `commit_set` signature/defaults/return types unpinned (core returns rows, porcelain returns Receipt); `AtomicAbort` MCP transport unspecified (a Python exception's attrs are not preserved by the dispatch envelope) | (§C4, §D) exact signatures + defaults (`classify="rules"`) + return types pinned; MCP dispatch serializes `cause` + `skipped` into the tool-error payload (not exception attrs); a wire oracle covers both causes. |

Frozen GREEN (r3): **F2** (model-free `rules\|defer` boundary), **F4**
(snapshot/restore mechanism + accurate mutable-view enumeration), **F5**
(shared-path retract target-validation; fixed internal dispatch; missing target
stays `cause=exception`), **F7** (non-idempotence + postcondition-probe).

### Prior round (r2 → r3) — for lineage

| finding | r2 defect (pbr, verified) | r3 resolution |
|---|---|---|
| **F1** RED | suppressing `_insert.commit()` is not the envelope — salience.py (57/67/94), classifier `_store`/rebuild, truth scan all `commit()` the SAME connection, committing the staged prefix mid-set | **buffer-owned unit-of-work** (§B1): while a unit is open, `commit()`/`rollback()` from *any* holder of the connection is gated to the unit's single terminal commit; nested unit entry is rejected. Fault matrix proves log + ALL sidecars stay uncommitted through every internal writer. |
| **F2** RED | the network-lock rationale is reversed — `ingest()` runs `extract()` *before* the write, so extraction is never in the transaction; the real hazard is `classify=inline\|batch` calling the model with the transaction OPEN | atomic V1 **requires model-free classification** (`classify ∈ {rules, defer}`; `inline`/`batch` under `atomic=True` is rejected, §A). `ingest()` stays non-atomic on the honest ground — an unmeasured, host-unauthored surface — not the lock reason. |
| **F3** RED | Oracle 3/G3 recipe is FALSE against the engine (pbr probed): the gate does not require a parent to pre-exist, so reverse order does not skip; constitutive containment does not recency-supersede, so a bare `grown.in=region` append leaves `locate()` at `old_parent` | G3 is now a **`commit_set` that retracts the old edge** then appends (§ defect, oracle 3). The order oracle uses a *genuine* order-sensitive case (recency-within-set / retract-of-staged), stated without any sort. Ordered execution is honest: author order, staged-prefix visibility, no repair. |
| **F4** RED | "invoke the rebuild path" is not an abort contract — no unified path, and `classifier.rebuild()` would delete/re-judge sidecar verdicts (maybe model calls) the SQLite rollback already restored | **explicit snapshot/restore** (§B4): snapshot the in-memory mutable views (`_alias_map` manual aliases, `_attribute_default_checked`, `AttributeSemantics` declaration view, classify collectors/toggles, `last_skipped`, porcelain cursor) before BEGIN, restore on abort; rollback restores rows; do NOT call `classifier.rebuild()`; retain skip diagnostics. Post-abort retry oracle. |
| **F5** RED | `TruthMaintenance.retract('a:missing', reason)` appends an orphan `retracts` row with no target validation (pbr confirmed) — the unknown-retract oracle cannot pass | **repair the shared standalone retract path** (§C1): validate the target exists (log or staged prefix) and raise on miss, so "existing path unchanged" is honestly true and both standalone + envelope benefit. Op schema rejects caller role/status; retract status fixed to `retracted`. |
| **F6** RED | failure shape under-specified ("raises or returns"); `Receipt` has no outcome field; fault coverage only at top-level items | **one frozen contract** (§B6): abort raises a typed `AtomicAbort` carrying receipts, success `Receipt` unchanged; gate-skip vs exception abort discriminated. Fault matrix injects at EVERY physical append/sidecar boundary + a cross-connection isolation probe + a post-COMMIT/pre-return fault. |
| **F7** YELLOW | "the host simply re-runs" is unsafe after COMMIT (a complete durable set + blind retry duplicates) | `commit_set` pinned **non-idempotent** (§B5); retry requires a postcondition probe; oracles cover both pre-commit rollback and post-commit durability. No claim that every crash implies rerun. |
| **F8** YELLOW | `commit_set` must be an explicit MCP destructive mutation with a discriminated `assert\|retract` ops schema (generic `list[dict]` insufficient) | §D: explicit MCP registry entry, discriminated ops schema, model-free narrowing (`rules\|defer`) preserved. |

GREEN in r2 and retained: storage-level atomicity belongs in the engine;
rollback of an uncommitted transaction respects append-only (no committed
assertion is edited/deleted); all-or-none is the correct meaning of
`atomic=True` and `atomic=False` already *is* commit-what-passed, so V1 needs no
partial knob; ordered ops are correct and the engine must not sort/repair author
input; `commit_set` as the general door plus `atomic=True` as assert-only sugar
is the right non-diluting surface.

## The measured defect

Ingest commits PER ROW (`buffer.py _insert` ends in `conn.commit()`) **and so
do the sidecar writers on the same connection** (salience, classifier, truth
maintenance). A fault mid-set therefore leaves a **committed visible prefix**.
The first host's WORLD-GROWTH program makes this a correctness wall, twice:

1. **A growth chunk** (place stub + containment + passage + protagonist move +
   anchored encounter + companion co-moves + texture). In G3 an ancestry
   *insertion* — a `region` interposed between `grown_place` and its existing
   constitutive parent — is a **mixed** operation, not a pure append: because
   constitutive containment does not recency-supersede (pbr probed this), the
   old `grown_place.in = old_parent` edge must be **retracted**, then
   `region.in = old_parent` and `grown_place.in = region` appended. A prefix
   of that is orphan or self-contradictory geography.
2. **An adoption set** (arc install + plot-frame index rows + old-main
   demotion + the manifest main-switch retract+append + receipt): a prefix is
   a manifest pointing at a half-installed arc.

Their reviewer's bar (correct, adopted): fault injection at EVERY row boundary
must show all-or-none visibility, and reopen recovery must deterministically
finish or roll back.

## Why this is substrate, not host anatomy

Atomicity of the log sits at the same tier as append-only and the two time
axes: a property of *how assertions become durable*, containing zero host
concepts. The storage engine already provides it — SQLite transactions — so the
engine is not acquiring machinery, it is *ceasing to commit too eagerly* and
*centralizing where the single commit happens*. Canon stays direct: no staged
frames, no pending markers, no resolver indirection.

Append-only is untouched: rolling back an **uncommitted** transaction edits
nothing — the rows never existed. No committed assertion is modified or deleted
by any path this spec adds. (pbr GREEN, r2.)

## A. The surface

`ingest_structured(items, frame=, classify=, cursor_authoritative=,
atomic=False)` — one new keyword, default `False` (existing behavior
byte-identical, including per-row visibility). Under `atomic=True`,
**classification must be model-free**: `classify ∈ {rules, defer}`. Passing
`classify=inline` or `classify=batch` with `atomic=True` raises `ValueError`
before any write — the honest V1 boundary, because those variants call the model
*inside* the open transaction and would hold the write lock across network time
(F2). Precomputing judgments before BEGIN and applying them inside is a possible
V-next, not V1.

`ingest()` (the model-backed extraction path) does NOT gain `atomic` in V1.
The reason is scope, not locking (F2 corrected): activation sets are
host-authored structured items; the extraction path has no measured all-or-none
case. (`extract()` already precedes the write in `ingest()`, so extraction was
never going to sit inside the envelope anyway.)

Exposed identically through `World.ingest_structured`, the porcelain, and the
MCP tool (additive param — porcelain-v0.1 compliant).

## B. Semantics under `atomic=True`

1. **A deny-by-default database capability facade (F1).** r5's enumerated
   forwarding proxy was still whack-a-mole; r6 inverts it. The buffer owns the
   sole SQLite connection and **never hands out a raw boundary** — every holder
   (`buffer._insert` itself, the salience sidecar, the classifier
   `_store`/rebuild, truth-maintenance) receives a **facade** built on an
   allowlist, closed by construction against sqlite surfaces pbr enumerated
   (`executescript` returns a cursor; native `cursor.execute/executemany` return
   `self`; Python 3.12 `Connection.autocommit=True` reveals an uncommitted
   prefix cross-connection; `close()`):
   - **allowlist, not blocklist.** The facade exposes ONLY the small set of
     methods and read-properties Pattern Buffer actually uses. Unknown
     attributes, setters, magic methods, and mutators are **not** forwarded —
     any access outside the allowlist raises. A new sqlite mutating/transaction-
     control surface is therefore denied by default, not newly leaked.
   - **every cursor-producing method returns a cursor proxy** — `execute`,
     `executemany`, `cursor`, and `executescript` (even when `executescript` is
     permitted, i.e. outside a unit). The cursor proxy's `execute`/`executemany`
     return **that same proxy**, never the native `self`; its `.connection` is
     the facade or unavailable. So no chain (`facade.cursor().execute(...)
     .connection`, `facade.executescript(...).connection`) recovers the raw
     connection.
   - **transaction control is provenance-gated, not owner-by-a-separate-channel
     (F1, the last boundary — r8 correction).** SQLite accepts transaction
     control as ordinary SQL, so a borrowed `facade.execute("COMMIT")` (or
     `facade.cursor().execute("ROLLBACK")`) would finalize the unit through an
     *allowed* method with no raw handle (pbr reproduced `A.execute("COMMIT")`
     revealing the prefix to B). AND — r7's error, pbr-falsified — Python
     `Connection.commit()`/`rollback()` themselves COMPILE `SQLITE_TRANSACTION`
     and are seen by the authorizer (`con.commit()` → `not authorized
     (22, COMMIT)`); there is no C-API that bypasses compilation. So a static
     deny/allow split cannot work: total-deny blocks the owner's own finalize,
     and allow re-opens the escape. r9 uses **provenance via an operation-specific
     phase**: during a unit the owner installs a **SQLite authorizer**
     (`set_authorizer`) that, at statement-COMPILE time, **denies**
     `SQLITE_SAVEPOINT`, `SQLITE_ATTACH`/`SQLITE_DETACH`, mutating `SQLITE_PRAGMA`,
     `VACUUM`, and DDL (create/drop/alter), and **allows** only PB's DML/read
     classes (`SQLITE_READ`/`SELECT`/`INSERT`/`UPDATE`/`DELETE`/`FUNCTION`). For
     `SQLITE_TRANSACTION` it consults an **unforgeable private phase**
     `_owner_phase ∈ {none, begin, commit, rollback}` (a closure-local/owner
     attribute, NOT reachable through the facade) and allows the compile ONLY when
     the phase equals the transaction operation being compiled (`begin`→BEGIN,
     `commit`→COMMIT, `rollback`→ROLLBACK); `none` denies all. Borrowed execution
     always runs at `phase=none` → any `execute("COMMIT")`/`BEGIN`/… is denied.
     - **Entry (F1.a) — default-path-neutral, no isolation change.** r9's
       manual-`isolation_level` idea is dropped: `isolation_level=None` is
       statement-level autocommit, and changing the sole connection globally
       would make existing non-atomic multi-statement writers (classifier
       `_store`: INSERT-OR-REPLACE → UPDATE → commit) independently durable — a
       default-path regression. Instead, **preserve the connection's existing
       transaction configuration**; install the authorizer; issue the explicit
       owner `BEGIN` on the raw connection under `phase=begin` (then reset to
       `none` via `try/finally`). Because a transaction is now already open, the
       first PB DML does **not** trigger an implicit BEGIN (the driver auto-BEGINs
       only when NOT already in a transaction — the owner's explicit BEGIN
       pre-empts it). No borrowed code runs between authorizer-install and that
       BEGIN (synchronous owner code), so there is no borrowed entry window, and
       a borrowed `BEGIN` stays denied at `phase=none`.
     - **Finalize + exception-safe teardown (F1.b).** For each owner transaction
       op the phase is set to exactly that op, the single raw call is issued, and
       the phase is **reset to `none` in a `try/finally`** — so a raised
       `commit()`/`rollback()` (including the rollback-unconfirmable case, §B6,
       where the raw error propagates unwrapped) can NEVER leave the phase
       authorizing. Single writer per world (§ non-goals) guarantees no
       reentrant/borrowed execution inside any phase window.
     - **Outer lifecycle — balanced install/restore (F1, r11).** The whole unit
       is an OUTER `try/finally`. On enter the owner saves any prior authorizer
       (owner-tracked internally — sqlite3 has no authorizer *getter*; the known
       prior in this design is `None`) and installs the unit authorizer; the
       finally **restores the prior authorizer (or removes it)** and leaves
       `phase=none`, on EVERY exit —
       commit success, confirmed rollback, and BEGIN failure — so the connection
       returns to its exact pre-unit state and the next non-atomic writer sees its
       normal implicit-BEGIN/commit path (the r10 escape: without this, a lingering
       `phase=none` callback denies the next ordinary INSERT's implicit BEGIN).
     - **Fail-closed on rollback-unconfirmable (F1, r11).** If the abort-path
       `rollback()` itself fails (the transaction may be partially applied and its
       state is unknown), the owner does NOT restore a reusable facade. It
       **poisons/closes the owner connection** — every later operation (borrowed
       or owner) raises — and propagates the raw error (F6, unwrapped). Uncertain
       state can never be finalized by a later borrowed `COMMIT`; the only exit is
       a fresh connection/reopen (where an uncommitted transaction is gone by the
       storage guarantee, §B5).
     `autocommit`/`isolation_level` setters and `close()` remain owner-only
     (rejected through a borrowed handle while a unit is open). A pure
     string classifier is **rejected** as porous (comments, `WITH`-prefixed
     statements); the authorizer enforces at the opcode, below the SQL text.
   - **`executescript`/DDL while a unit is open is rejected** (`RuntimeError`;
     no activation path needs DDL); it implicitly commits before running, so it
     can never be permitted mid-unit.
   - **schema-ensure vs. rebuild (no-degradation).** Salience `_ensure_schema`
     runs `executescript` on *every* access today (salience.py:53/65/79). r6
     makes `salience()` reads **DDL-free** (a create-once guard); but
     `salience_index.rebuild()` legitimately recreates the table — the recovery
     path `test_salience_rebuild_parity` drops `sidecar_salience` and expects
     `rebuild()` to bring it back. So `rebuild()` keeps an explicit recreate,
     permitted **outside** a unit and **rejected during** one (the facade's
     open-unit DDL rejection covers it). Recovery works; the escape is closed.
   Nested unit entry is **rejected** (`RuntimeError` — an activation set is not
   re-entrant). On clean completion: one commit; the set becomes visible as a
   unit. On any exception: one rollback. The fault matrix (oracle 1) proves the
   log AND every sidecar — including the salience `_ensure_schema` path — stay
   uncommitted through every internal writer *and every implicit boundary*, via
   a second-connection isolation probe, not merely `buffer.append`.
2. **All-or-none extends to gate skips.** Non-atomic gate receipts a bad edge
   and continues; under `atomic=True` any such **skip** (malformed id, cycle,
   self-edge — exactly the conditions that receipt-and-continue on the
   non-atomic path) aborts the whole set: rollback, nothing visible,
   `AtomicAbort(cause=gate_skip)` (§B6) carrying the receipts. (Authority
   violations and semantics conflicts are NOT skips — they RAISE on the
   non-atomic path, so under `atomic=True` they surface as
   `AtomicAbort(cause=exception)`, §B6, never reclassified.) Receipts remain
   **carried on the exception, never rows**: technical failure stays outside
   canon by construction.
3. **Ordered execution, author order, no repair (F3).** Ops/items apply in the
   order given; each observes the staged prefix (uncommitted rows are visible to
   the writing connection, so op *k*'s cycle/ancestry/recency checks see ops
   1..k−1). The engine **never sorts or repairs** author order. The one
   contractual order-effect is **recency within a set**: two asserts of the same
   `(entity, attribute)` leave the LATER one the fold winner. **Retract-of-staged
   is NOT a V1 contract (F3):** an assert's row id is auto-assigned `a:<seq>`
   *during* execution, but a `retract` op must carry a concrete `assertion_id`
   *before* execution — predicting head offsets is not a public contract and
   would break the moment an assert emits declaration/meta-rows. **Retract target
   eligibility is the pre-call committed-id snapshot (F3):** a `commit_set`
   retract may target only an assertion committed BEFORE the call — never one an
   earlier op in the same set minted (whose `a:<seq>` id is not public
   vocabulary). Staged-prefix visibility still applies to cycle, ancestry, and
   recency checks — just NOT to retract target eligibility. (Standalone
   `retract` validates against its call-time log, which is the same committed
   snapshot for a single call.) A symbolic op-result-reference vocabulary
   (retract op N's result) is V-next, only if a measured case forces it — no
   offset-prediction ships. Containment parent/child order is NOT gate-enforced
   (pbr: the gate does not require a parent to pre-exist); r2's "reverse
   containment skips" claim stays retracted. Authoring scaffold-first remains
   good discipline, not a gate contract.
4. **Explicit snapshot/restore on abort (F4).** SQLite rollback restores all
   durable state — the log rows and the sidecar rows alike (they rode the one
   unit). What rollback does NOT restore is **in-memory mutable view state** that
   was mutated during the call; that is snapshotted before BEGIN and restored on
   abort:
   - `Ingestor._alias_map` (manually added aliases), `_attribute_default_checked`
     — real leaks pbr named; snapshot + restore exactly.
   - `AttributeSemantics` in-memory declaration view; classify collectors and
     toggles; `last_skipped`.
   - the porcelain `at=` cursor: a failed atomic call **restores its prior
     cursor** (pbr recommended yes; adopted).
   The abort does NOT call `classifier.rebuild()` — that would delete and
   re-judge (possibly with model calls) sidecar verdicts the rollback already
   restored. Only cheap log-derived views (identity registry closure) recompute
   from the rolled-back log; identity proposals/closure are log-computed and do
   not leak (pbr). **Two exact pins (F4, pbr):** (a) the porcelain snapshots its
   prior cursor position BEFORE it applies `at=` — not after entering the
   lower-level call — so the restored cursor is genuinely the pre-call value;
   (b) "restore `last_skipped`" and "preserve diagnostics" have one meaning: the
   object's `last_skipped` is restored to its prior value, while THIS abort's
   skip receipts ride out on the `AtomicAbort` (§B6) — the two never alias.
5. **Crash and reopen (F7).** A process death before the commit is an
   uncommitted SQLite transaction — gone on reopen, by the storage engine's
   guarantee; in-memory views rebuild from the log at open as they already do.
   There is no "finish forward" branch: rollback is the only partial-fault
   outcome. BUT `commit_set`/atomic ingest is **non-idempotent** — a death or
   response-loss AFTER commit leaves a complete, durable set, and a blind re-run
   would duplicate the operations. Recovery contract: on an ambiguous outcome
   the host **probes a postcondition** (is the new main loadable? does the head
   carry the set?) before deciding to retry. Atomicity is not exactly-once; the
   spec does not claim every crash implies a safe rerun.
6. **One frozen failure contract, taxonomy-correct (F6).** On abort the call
   raises `AtomicAbort` (public import `patternbuffer.AtomicAbort`, re-exported
   from `patternbuffer.tmaint`) with payload `{cause, skipped, error}`. Field
   TYPES are frozen, not only names:
   - `cause`: the string `"gate_skip"` or `"exception"`.
   - `skipped`: a list of the existing skip-receipt records
     `{entity, attribute, value, reason}` (the same shape the non-atomic path
     already returns) — `[]` when `cause="exception"`.
   - `error`: `null` when `cause="gate_skip"`; `{type, message}` when
     `cause="exception"`.
   The taxonomy **mirrors the non-atomic path exactly** so the default surface
   stays byte-identical: `gate_skip` covers ONLY the receipt-and-continue skips
   (malformed id, cycle, self-edge); `exception` covers the conditions that
   already RAISE (authority violation, semantics conflict, unknown retract
   target §C1, or an unexpected error) — never reclassified to skips. `error`
   wraps the original (`type` + `message`).
   `AtomicAbort` is emitted **only after rollback is confirmed**. A fault AFTER
   the terminal COMMIT (before return) is **not** an abort and is never wrapped
   as `AtomicAbort` — the set is durable and complete (the F7 ambiguous outcome,
   resolved by the postcondition probe). If rollback ITSELF cannot be confirmed
   (a failure during rollback), the surface is **not** `AtomicAbort` either — it
   is the raw underlying error propagated unwrapped, so a caller never reads
   "clean rollback" from a rollback that did not complete. The success `Receipt`
   shape is unchanged (no new field on the happy path); the call never returns a
   partial `appended` list.

## C. The typed operation set — `commit_set` (closes the adoption gap)

The adoption set is NOT assertion-only — the manifest main-switch retracts
constitutive control rows (constitutive folds do not recency-supersede, by
design), and §A's `atomic=True` surface appends assertions only.

**The decisive engine fact:** `retract` is itself an APPENDED meta-assertion
(`tmaint.retract` → one `retracts` row; the target survives in the log). At the
log level a mixed set is pure appends, and the §B unit-of-work covers it with
ZERO change to the atomicity story. The gap was only ever the call surface.

1. **`commit_set(ops)` — one porcelain verb, the general door.** `ops` is an
   ordered list; V1 vocabulary is exactly two: `{op: "assert", item: {…}}` (an
   ingest-gate item, full discipline) and `{op: "retract", assertion_id,
   reason}` (the truth-maintenance verb). Each op dispatches through its
   EXISTING path — gate discipline, canonicalization, and the role-authority
   matrix apply per-op exactly as today; the unit-of-work changes only WHEN
   durability happens. **Authority is not laundered** (pbr): the dispatcher
   calls `TruthMaintenance.retract`, whose capability is held internally, just
   as the standalone verb; the op schema accepts **no** caller-supplied role or
   status, and retract status is fixed to `retracted`.
   **Shared-path repair (F5), validated against the committed snapshot (F3):**
   `TruthMaintenance.retract` today appends an orphan `retracts` row for a
   missing target. r5 adds **target validation to that shared standalone path** —
   it raises on a target absent from the **pre-call committed log** (NOT the
   staged prefix; §B3: a staged `a:<seq>` id is not addressable) — so the fix
   lands once and "existing path unchanged" stays honestly true (standalone
   retract, a single call, validates against the same committed log). Under the
   envelope a missing or staged-only target is an `exception`-cause abort (§B6).
2. **`ingest_structured(items, atomic=True)` is sugar** for the assert-only set
   — one primitive, one general door plus one convenience parameter, so the
   anti-dilution criterion holds: `atomic=True` when everything is an assertion,
   `commit_set` when anything isn't. (pbr: keep the sugar relationship.)
3. **Option B (re-model the manifest so the fold latest-wins) is REJECTED:**
   main-arc-ness is deliberately constitutive so recency can never accidentally
   supersede a control row; weakening the fold to dodge a surface gap trades a
   real invariant for convenience and pushes engine-shaped pressure into host
   data-modeling.
4. **Not a transaction API:** `commit_set` is one call with a declared op list —
   no open-transaction context manager, no cross-call envelope. An activation is
   data, not a code block.
5. **Exact signatures, defaults, and return types (F8) — reconciled with the
   real `ingest_structured` default.** `ingest_structured` defaults
   `classify="inline"` today (ingest.py:310, porcelain:287); the sugar cannot
   silently "share `classify=rules`". Pinned:
   - **`ingest_structured` keeps `classify="inline"`.** Under `atomic=True`, an
     omitted/`inline`/`batch` classify raises `ValueError` before any write
     (model-free required, §A); the caller passes `classify="rules"` or
     `"defer"` explicitly. This preserves default-path fidelity (omitted classify
     ⇒ inline ⇒ the existing behavior when `atomic=False`).
   - **`commit_set` is a NEW verb → defaults `classify="rules"`** (no back-compat
     to preserve): core
     `World.commit_set(ops: list[dict], *, classify: str = "rules",
     frame: str = CANON, cursor_authoritative: bool = False) -> list[Assertion]`
     (returns appended rows, matching `ingest_structured` core); porcelain
     `commit_set(ops, *, classify="rules", frame=CANON,
     cursor_authoritative=False) -> Receipt` (the `Receipt` idiom, unchanged on
     success). `classify` narrowed to `{rules, defer}`.
   - MCP continues injecting `rules` via its own existing schema override; the
     Python default divergence (inline for the sugar, rules for `commit_set`) is
     intentional and documented, not an inconsistency.

## D. MCP registration + wire contract (F8)

`commit_set` is added to the **explicit** MCP tool registry as a **destructive
mutation** (not generic reflection), with a discriminated ops schema —
`oneOf: [{op:"assert", item}, {op:"retract", assertion_id, reason}]` — so a
generic `list[dict]` never reaches the gate unshaped. The MCP model-free
narrowing is preserved: `atomic`/`commit_set` accept `classify ∈ {rules,
defer}` only.

**`AtomicAbort` transport — exact envelope (F8, pbr).** The current call wrapper
returns the success envelope and lets exceptions fall through to generic SDK
tool errors, which do NOT preserve exception attributes. So on `AtomicAbort` the
dispatch layer emits a **pinned tool result**:
`{ isError: true, structuredContent: {cause, skipped, error}, content:
[{type: "text", text: <human summary>}] }` — the machine-readable
`structuredContent` is the contract (`cause`/`skipped`/`error` with the §B6
types); the `content` text is a fallback summary, not parsed. A **wire oracle**
asserts the exact bytes for both causes end-to-end through MCP: a `gate_skip`
abort (malformed id → `structuredContent.skipped` populated, `error: null`) and
an `exception` abort (unknown retract target → `cause:"exception"`,
`skipped: []`, `error:{type,message}`), each leaving the world byte-identical to
pre-call. The fixture pins the literal JSON shape, not just field presence.

## Out-of-scope constraints the host asked about (ruled, no engine surface)

- One-activation-per-turn is host budget policy; the engine enforces nothing.
- Journey-time pricing "only after successful activation" is trivially ordered:
  success IS the commit returning.

## Oracles

1. **The fault matrix** (the reviewer's bar, made a loop): for an N-op set,
   inject a fault at every boundary — before op 1, between every pair, before
   the final commit — AND at every *physical* append/sidecar boundary within an
   op (attr declarations, canonicalization/source/learned-at/correction/same_as/
   alias meta-rows, classifier + salience sidecar rows), not merely top-level
   ops (F6). At each: head unchanged, zero rows visible, `entities()`/`locate()`/
   `snapshot()` identical to pre-call, and — the F1 bar — a **second SQLite
   connection sees nothing** before COMMIT (cross-connection isolation), through
   every internal writer **and every implicit boundary** — including an explicit
   probe that forces the salience `_ensure_schema()`/`executescript` path during
   an open unit and asserts the staged prefix stays invisible and a rollback
   still removes it (the exact escape pbr reproduced). After the unfaulted run →
   all rows visible, contiguous `seq`. A fault **after the terminal COMMIT /
   before return** is NOT an abort (§B6): the set is fully durable and complete,
   and the F7 postcondition probe — not `AtomicAbort` — is what the host runs.
2. **Skip aborts the set:** one malformed id (or one cycle-forming edge) at
   position k → `AtomicAbort(cause=gate_skip)`, nothing visible, receipts name
   exactly that edge; the same set minus the bad edge commits whole.
3. **G3 ancestry insertion, as a mixed set (F3):** a `commit_set` =
   `[retract(grown.in=old_parent), assert(region.in=old_parent),
   assert(grown.in=region)]` — after commit `locate(grown)` returns `region`
   and `locate(region)` returns `old_parent`; a bare append-only version
   (no retract) is shown to LEAVE `locate(grown)=old_parent` (the pbr probe,
   captured as the negative fixture). A fault before/after any boundary leaves
   the original edge fully readable.
4. **Order-sensitivity, no sort (F3):** recency-within-set is **world-time
   progression**, not log order (indexes._fold_state, "log order alone must never
   pick a truth"): with **progressing coordinates**, `[assert x.a=1 @t5,
   assert x.a=2 @t6]` leaves `state(x.a)=2`; the reversed authoring
   `[assert x.a=2 @t5, assert x.a=1 @t6]` leaves `1` (value 1 carries the later
   `valid_from`). Equal-`valid_from`/different-value is a flagged simultaneous
   contradiction, NOT an update — so the ordering contract rides `valid_from`, and
   the engine reorders neither the ops nor their coordinates. The eval asserts the
   **returned/physical append order follows the authored op list** (a winner-only
   check would also pass a `valid_from`-sorting impl). No topological repair
   anywhere. *(pbr r12 concurrence — the r11 example wording assumed progressing
   coordinates; made explicit here.)*
4b. **Retract targets the committed snapshot, not the staged prefix (F3, the
   negative oracle):** `[assert x.a=1, retract(<the a:<seq> id that assert would
   mint>)]` → `AtomicAbort(cause=exception)` (the staged id is not an eligible
   target), whole set rolled back. Cycle/ancestry/recency checks still see the
   staged prefix — only retract eligibility is committed-snapshot-only.
5. **The adoption set, on the real operation surface** (cr's oracle, verbatim):
   a `commit_set` mixing retracts (constitutive manifest control rows) and
   appends (new main + arc + index rows) — a fault before or after EVERY
   retract/append boundary leaves the old main fully readable; success leaves
   exactly one fully loadable new main. A retract op naming an unknown
   assertion_id aborts the whole set (`cause=exception`).
6. **Snapshot/restore on abort (F4):** a set that (i) adds a manual alias, (ii)
   trips `_attribute_default_checked`, (iii) advances the porcelain cursor, then
   faults → after abort the alias map, the default-checked set, and the cursor
   are **byte-identical to pre-call**, `classifier.rebuild()` was NOT invoked,
   sidecar verdicts are intact (restored by rollback, not re-judged), and a
   **post-abort retry** of a clean set behaves exactly as a first run.
7. **Standalone retract repair (F5):** `retract('a:missing', reason)` on the
   standalone path now RAISES (no orphan `retracts` row appended); a valid
   target still retracts as before.
8. **Crash simulation (F7):** kill the connection pre-commit; reopen → nothing
   visible, in-memory views consistent, the re-run commits clean. Separately:
   after a successful commit, a simulated response-loss + blind re-run is shown
   to DUPLICATE (documenting non-idempotence), and the postcondition-probe
   recipe avoids it.
9. **Model-free enforcement + the reconciled default (F2, F8):**
   `ingest_structured(atomic=True)` with `classify` OMITTED (→ the `inline`
   default) raises `ValueError` before any write — the default is not silently
   promoted to `rules`; the same call with an explicit `classify="rules"` or
   `"defer"` composes (sidecar rows in the same unit); `classify="batch"` also
   raises. `commit_set` with omitted classify uses its own `rules` default.
   `ingest()` exposes no `atomic` param.
10. **Default-path pin:** `atomic=False` (and all existing callers) remain
    byte-identical — per-row visibility, per-row commit, receipt-and-continue
    skips. **(F1.a, r10)** the connection's `isolation_level` is UNCHANGED from
    today, and a non-atomic multi-statement sidecar writer (classifier `_store`:
    INSERT-OR-REPLACE → UPDATE version → commit) exhibits the SAME
    statement-grouping and durability boundary as before this spec — proving the
    entry mechanism introduced no autocommit regression. **(F1 exit, r11)** on
    the SAME connection, an ordinary non-atomic writer run AFTER an atomic
    SUCCESS and AFTER an atomic confirmed-ABORT both work normally (implicit
    BEGIN/commit + `_store` grouping intact) — proving the authorizer was
    restored/removed, not left lingering.
11. **Meta-rows ride the unit:** a set whose ingestion mints canonicalization
    receipts and first-use `attr:*` declarations rolls those back with the data
    rows on abort (no orphan declarations).
12. **Failure taxonomy is byte-identical to non-atomic (F6):** authority
    violation and semantics conflict under `atomic=True` raise
    `AtomicAbort(cause=exception, error=<the original>)` — NOT `gate_skip` — and
    the SAME inputs on the non-atomic path raise exactly as they do today
    (the conversion-to-skip that would break parity never happens); malformed
    id/cycle/self-edge are `cause=gate_skip`. `AtomicAbort` is observed only
    after rollback is confirmed.
13. **MCP wire result (F8):** through the MCP dispatch, a `gate_skip` abort
    parses to `isError=true` with `structuredContent = {cause:"gate_skip",
    skipped:[…records…], error:null}` and an `exception` abort to
    `{cause:"exception", skipped:[], error:{type,message}}`. The oracle compares
    the **parsed `CallToolResult`** (not literal JSON bytes — key ordering is not
    semantic, pbr F8), and the human `content` text is non-contractual. Both
    leave the world byte-identical to pre-call.
14. **Capability facade is deny-by-default and leak-closed (F1):** the facade is
    the ONLY obtainable handle; each escape is probed pre-BEGIN and proven dead
    during a unit — `facade.execute("select 1").connection`,
    `facade.cursor().execute(...).connection` (chained),
    `facade.executescript(...).connection` (outside a unit), and
    `facade.__enter__()` all yield the facade (or no raw connection); `commit`/
    `executescript` through any borrowed handle during a unit is a
    no-op/`RuntimeError`; assigning `facade.autocommit = True` during a unit
    raises (owner-only) while a second connection proves the prefix stays
    invisible; `close()` through a borrowed handle raises mid-unit.
    **SQL-class denials + provenance lifecycle (F1, r9):** during a staged unit,
    `facade.execute("COMMIT")` and `facade.cursor().execute("ROLLBACK"/"END")`
    each raise (`phase=none`) while a second connection sees no prefix.
    **Entry (F1.a, r10):** with the connection's isolation config UNCHANGED, the
    owner's explicit BEGIN + the first PB DML succeed (the DML triggers no second
    implicit BEGIN because the explicit one already opened the transaction), while
    a borrowed `execute("BEGIN")` stays denied — proving a borrowed-window-free
    entry without any autocommit/default-path change. **Finalize:** the owner's terminal `commit()` succeeds
    (`phase=commit`) and an exception-path `rollback()` succeeds
    (`phase=rollback`), second-connection visibility all-or-none across both.
    **Exception-safe teardown (F1.b):** inject a failure in the raw
    `commit()`/`rollback()` → afterward `_owner_phase` is `none` and a subsequent
    `facade.execute("COMMIT")` is still denied (the `try/finally` reset holds even
    when the terminal call raises). **Fail-closed poison (F1, r11):** inject a
    rollback-UNCONFIRMABLE failure → the raw error propagates (F6) AND the owner
    connection is poisoned/closed — every subsequent operation (a borrowed
    `execute("COMMIT")`, any read, the facade at large) raises, proving uncertain
    state can never be finalized; only a fresh reopen recovers (uncommitted work
    gone by the storage guarantee). The same denials
    hold for representative `SAVEPOINT`/`RELEASE`, mutating `PRAGMA`, `ATTACH`, and
    DDL, while the exact `SELECT`/`INSERT`/`DELETE` sidecar statements PB uses keep
    working inside the unit. A **deny-by-default assertion** covers
    BOTH Python attributes AND SQL operation-classes reachable through allowed
    methods, and FAILS if any new sqlite mutating/transaction-control surface
    becomes reachable (future-proofing as a test, not vigilance). `salience()`
    reads run no DDL; `salience_index.rebuild()` recreates `sidecar_salience`
    OUTSIDE a unit (`test_salience_rebuild_parity` still passes), rejected inside.
15. **No-degradation:** full suite green; every same-connection sidecar writer
    (salience, classifier) is shown to defer its commit under an open unit and
    to commit normally outside one.

## Non-goals (pinned)

- No cross-call transactions, no nesting, no long-lived open transaction
  surface (an activation set is one call; `commit_set` takes data, not a code
  block; nested unit entry is rejected, not supported).
- No op vocabulary beyond `assert` | `retract` in V1 (merge, correlate,
  adjudicate wait for a measured multi-op case; each needs its own
  authority/derived-state audit before entering the envelope). **Tripwire:** a
  host activation that cannot be expressed as ordered assert/retract.
- No visibility indirection: no staged frames, no pending status, no activation
  meta-row in canon. Atomicity is storage-level or nothing.
- No model-backed classification inside the envelope in V1 (`inline`/`batch`
  rejected under `atomic`). **Tripwire:** a measured set needing LM
  classification atomic with its rows → the precompute-before-BEGIN design.
- No `ingest()` (extraction-path) atomicity in V1 — no measured case.
- No multi-world or cross-buffer transactions (1 world ↔ 1 buffer stands).
- No concurrency model change: one writer per world, as today.
- No exactly-once / idempotent retry (F7): `commit_set` is non-idempotent by
  contract; safe retry is the host's postcondition-probe responsibility.
- No host-budget enforcement (one-per-turn stays host policy).

## Docs on ship

ADOPTION (the `atomic=True` + `commit_set` contract, the ordering rule, the
`AtomicAbort` outcome, the non-idempotence + probe recipe), INGESTION-PLAYBOOK
(activation-set recipe: scaffold-first ordering, model-free classify,
receipts-on-abort), LEXICON (**activation set**, **unit-of-work** — one term
each), WHITEPAPER decision record (atomicity tier note; the centralized-commit
ownership), STATUS.md.
