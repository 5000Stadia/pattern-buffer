# FOLD-CORRECTNESS-V1: one set of fold rules across classes, ties and time

**Status:** DRAFT r3 (2026-10-08).
- r2 recorded the build's clarifications.
- r3 resolves the internal pre-review (RED → fixed; see "r3" at the end), which
  withdraws two r2 bullets.

The gated implementation is on `impl/fold-correctness-v1`. Not yet reviewed by
pbr. Built from batch A of
`docs/AUDIT-2026-10.md`, which reproduced every case below. It changes served
answers only where today's answers are wrong. It waits on Kabe's go-ahead before
review. Construct asked for §3 in particular, since its player moves every few
turns.

**Why.** The fold is the engine's one source of current truth, and its rules are
applied unevenly:
- evidence rank governs STATE but not DISPOSITIONAL or CONSTITUTIVE;
- a tie inside one source class ends the fold before other classes are heard;
- `valid_from == 0.0` reads as "no time" at four sites;
- the tie tests compare raw value text where every other comparison resolves
  identity.

Each one serves a wrong answer on ordinary input (audit P1 #2, #3, #9, and P2's
value-identity finding).

## §1 One recency key

`_recency_key(row) = (row.valid_from if row.valid_from is not None else -inf,
row.asserted_at)`.

It replaces `(r.valid_from or float("-inf"), r.asserted_at)` at
`indexes.py` (the DISPOSITIONAL max and `_fold_state`'s per-class top) and at
`project.py` (the containment-parent pick and `_establishing_state`). Three
other sites in `indexes.py` already spell it this way. The cursor starts at 0.0,
so rows at t=0.0 are common.

**Oracle:**
- `in room:now` stamped at 0.0 and `in room:flashback` stamped at −10 (same
  class) serve `room:now`. Today they serve `room:flashback`.
- The same holds for `establishing_set` and the containment walk.

## §2 One value identity for every tie test

`_value_key(row)` is `("entity", resolve(value))` for an entity-valued row and
`("literal", repr(value))` otherwise. It is today's CONSTITUTIVE comparator,
lifted to a method. Every tie test in `_fold_state` uses it:
- the per-class tie;
- the containment current set.

`_values_agree` stays directional for literals. When both rows are
entity-valued, agreement is resolved-id equality.

**Oracle:**
- A coin placed `in purse` and `in pouch` at the same time is conflicted.
- After `merge(purse, pouch)` it serves one container, unconflicted. Today it
  stays conflicted.

## §3 A stale tie never outvotes a later move (containment family)

For the containment family, `_fold_state` no longer returns on a per-class tie.
Instead:
1. Each source class contributes the rows at its own latest `valid_from`: one
   row, or a tied set.
2. `top_vf` is the latest of those across classes.
3. The **current** rows are every contributed row at `top_vf`.
4. If their `_value_key`s differ, the fold is conflicted. It serves the
   earliest-asserted current row, with `conflicting` set to all current ids.
   Otherwise it serves the latest-asserted current row.

With one source class this reduces exactly to today's behaviour: a tie at the top
is a conflict.

**Oracle:**
- `speaker:gossip` puts p `in room:a` and `in room:b` at t=1, and the narrator
  moves p to `room:c` at t=10. `locate(p)` is `[room:c]`, unconflicted, in
  either insertion order. Today it is `[room:a]` forever.
- A same-time cross-class disagreement at the top still flags.

**Non-goal: non-containment keys keep today's early return.**
- Across classes a non-containment disagreement already flags under §7.2, so a
  stale in-class tie there changes only *which* conflict is reported, never
  whether a correct value is served.
- Revisit if a host measures a case.

## §4 Evidence rank governs every durability class

- **CONSTITUTIVE:** filter to the top evidence rank first (the `_fold_state`
  rank table, unchanged). Then serve the earliest row, flagging any `_value_key`
  disagreement among that rank.
  - Structure still outranks recency, and structure still outranks the other
    classes.
  - A later *stated* `kind` now overrides an earlier *inferred* one. Today the
    inferred one wins.
- **STATE ∪ DISPOSITIONAL** fold together through `_fold_state`, with the same
  rank, source-class and recency machinery. DISPOSITIONAL no longer has its own
  branch that skips rank and §7.2.
  - Typical DISPOSITIONAL rows are timeless (`valid_from` None), so any timed
    STATE row still supersedes them, as today.
  - A *timed* DISPOSITIONAL row now competes on recency instead of always losing
    to STATE.

**Oracle:**
- A stated "plays violin" followed by a later *inferred* "cello" (both
  DISPOSITIONAL) serves violin. Today it serves cello.
- After `promote_accruals` turns cheerful@1,2,3 into DISPOSITIONAL, grumpy@0.5
  (STATE) no longer wins; cheerful@3 is served.
- An inferred `kind person` and a later stated `kind place` serve `place`.
- Two stated DISPOSITIONAL values from two source classes flag (§7.2).

## §5 As-of reads stay as-of

`_establishing_state`'s `world_defining` pin lookup passes `asserted_as_of`.

**Oracle:** a pin appended after H does not change `materialize(...,
asserted_as_of=H, lens="establishing_set")`.

## §6 Time values are numbers at the gate

After cursor stamping, `valid_from` and `valid_to` must each be None or a finite
real number (an `int` or `float`, never a `bool`). Anything else is skipped with
reason `invalid_valid_time` and the offending value in `detail`. Under
`atomic=True` this aborts the call through the existing `gate_skip` path.

Today a text `valid_from` ("spring 1660") is admitted and then crashes `state`,
`locate` and `snapshot`, and NaN is admitted. The extractor prompt invites dated
text, so this is reachable on the prose path.

**Oracle:**
- `"spring 1660"`, `NaN`, `inf` and `True` are each skipped with a receipt.
- An integer year is admitted.
- Reads on the key keep working.

## §7 The private family key never leaves the engine

`__containment__` is an internal fold key. At the read boundary:
- `current_state`'s keys and `snapshot`'s `conflicted` list name the family as
  `in`.
- `neighborhood(edge_kinds=["relations"])` excludes every containment-family
  attribute (today it returns the containment parent as a relation).

Hosts never received the sentinel by contract. Construct and holo-emitter were
checked and neither reads it.

## Non-goals

- Changing CONSTITUTIVE's precedence over STATE/DISPOSITIONAL.
- Non-containment stale ties (§3).
- Salience's own as-of gap. It affects ranking only and goes with the
  read-cache work.
- Any change to the log, the sidecar schema, or the porcelain's signatures.

## Migration and notice

None: every change is in derived reads or at the gate. Existing logs re-fold
under the new rules on the next read. Ship notice to construct, listing the
answers that change (§1, §3, §4) so it can re-baseline any golden play logs.

## Tests

One test per oracle above, in `tests/test_fold.py` (§1–§4),
`tests/test_situation_lens.py` (§5), `tests/test_ingest_hardening.py` (§6) and
`tests/test_world_retrieval.py` (§7). The full suite must stay green. Any
existing test whose expectation encodes one of the wrong answers above is
updated in the same commit, with the audit finding cited.

## r2 clarifications (from the gated build)

- **§4, across sources.** "A timed STATE row still supersedes a timeless habit"
  holds within one source class. Across classes, a disagreement between them now
  raises the §7.2 flag instead of silently serving STATE, which is the
  whitepaper's cross-source rule applied to habits too.
- ~~**§4, within one source.** A timeless STATE row and a timeless DISPOSITIONAL
  row with different values tie at the same (absent) time, so they now
  conflict.~~ **Withdrawn in r3.**
  Two undated contradictory standing claims are a contradiction to surface, not
  a silent STATE win.
- ~~**§4 in the establishing lens.** The establishing view serves a
  DISPOSITIONAL winner as is.~~ **Withdrawn in r3.**
- **§6 receipt.** `SkipRecord` gains an optional `detail` (the offending value).
  It is emitted only when set, so every existing receipt is byte-identical.
- **§7 leftovers.**
  - The sentinel remains reachable through the engine-internal
    `Indexes.fold_attribute()`/`key_rows()`. Neither is porcelain.
  - Salience was re-keyed, so its scores are unchanged.
  - Resolver prompt lines now say `in`.
- **§3 conflict order.** A cross-source containment conflict lists its rows in
  assertion order (previously id-string order). The set is the same.
- **Blast radius, measured on fresh copies:**
  - case-1660: §1–§6 change nothing; §7 renames 55 keys.
  - anchor (§1): `place:anchor water_allocation_balance`'s establishing value
    becomes the earliest row (t=−3650), no longer the t=0.0 one.
  - anchor (§4): `person:pell duty_assignment` serves the later DISPOSITIONAL
    deputy_warden (t=14) over off-shift (t=3).
  - anchor (§7): 44 keys renamed. Default neighborhoods are unchanged
    everywhere.

## Internal pre-review (2026-10-08): RED. Fix before pbr

Measured on 9 real worlds (anchor, plus 8 of construct's) and a 4000-log fuzz.
The reviewer's tested patch for findings 1–2 is
`specs/FOLD-CORRECTNESS-V1-prereview-fixes.diff` (601 pass with it).

1. **MAJOR: the establishing view serves the latest habit.** r2's "serves a
   DISPOSITIONAL winner as is" breaks §13's "first non-event-effect value" and
   ignores `world_defining` pins. The at-rest view then changes with later
   events. Construct's opening screen reads this lens.
   - Fix: send a DISPOSITIONAL winner through `_establishing_state` too, and
     keep it as is only when no establishing STATE row exists. Withdraw the r2
     bullet.
2. **MAJOR: same-time ties between standing rows now conflict.** This includes
   a STATE row against a habit. Construct writes two drives per character at
   one stamp, so all 6 bodycase drives become conflicted and 4 change value.
   Emberroad and thedeep are hit too.
   - Fix (both tie tests): at one instant a STATE row outranks a habit with the
     same stamp, and habit-only ties don't flag (base behaviour). Withdraw r2's
     "within one source" bullet.
3. **Minor (§6): numeric strings.** A numeric string time ("1660") used to work
   and is now dropped. Coerce strings that parse as a finite float.
4. **Nits.**
   - Ints ≥ 2**63 crash the insert (old bug).
   - §2's identity is current, so a `same_as` merge now erases ties in as-of
     reads from before the merge.
   - The ship notice must list construct's worlds: 12 `locate()` changes, all
     correct §1/§3 fixes.
   - `"timeless": "false"` as a string makes a row timeless.
   - A bad `at=` poisons the cursor.

## r3: the pre-review resolved

1. **§4a: the at-rest view stays at rest.** In `establishing_set`, a
   DISPOSITIONAL fold winner also goes through `_establishing_state` (the first
   non-event-effect STATE, which honours `world_defining`). The habit is served
   as is only when no establishing STATE exists.
   - Oracles: Pell's at-rest duty stays `off_shift` under a later habit, and a
     pinned `under_siege` survives promoted `rationing`.
2. **§4b: same-stamp standing rows.**
   - At one instant, a STATE row ("right now") outranks a habit stamped with it,
     and is not a contradiction.
   - Habits tied at one instant coexist (an NPC's drives), as they did before
     this spec.
   - Only STATE rows tied with different values conflict.
   - This applies in both tie tests: the containment current set and the
     per-class tie.
   - Oracles: construct's two-drives-at-one-stamp shape is known and not
     conflicted; two tied STATE moods still conflict.
3. **§6 coercion.** A numeric string ("1660") is coerced to a float rather than
   skipped (SQLite used to coerce it silently, and it worked). An int beyond
   SQLite's 64-bit range becomes a float instead of crashing the insert. Text,
   NaN, inf and bool are still skipped.
4. **Noted, not changed.**
   - §2 compares identities as they stand now. An `asserted_as_of` read from
     before a merge sees the two values as one. This is identity's known as-of
     limitation, out of scope here.
   - `"timeless": "false"` as a string, and a bad `at=` poisoning the cursor,
     go to GATE-AUTHORITY-V1's item normalization.
5. **Ship notice.** It must also list construct's played worlds: 12 `locate()`
   answers change (thedeep 8, ironhold 2, emberroad2 1, a live world 1), all
   correct §1/§3 fixes. With r3, the reviewer measured no other changes to
   construct's worlds beyond the intended §1–§4.
