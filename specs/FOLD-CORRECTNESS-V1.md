# FOLD-CORRECTNESS-V1: one set of fold rules across classes, ties and time

**Status:** DRAFT r1 (2026-10-08). Not yet reviewed by pbr. Built from batch A of
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
