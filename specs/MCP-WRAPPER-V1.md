# MCP-WRAPPER-V1 — the porcelain over MCP: the engine-independence proof, non-Python

**Status:** SHIPPED — spec: Cx BLOCKED (521: four contract gaps) → r2 GREEN (529).
Implementation: Cx BLOCKED (533: postponed-annotations schema bug — 83 params
silently permissive, fixed at source with fail-closed registry build; missing
lifecycle/acceptance tests — added) → BLOCKED (535: SDK v2 pin) → **final GREEN
(539)**. 446 green; installed-package stdio smoke PASS. All review on the
codex-inbox channel. The whitepaper's reserved "later optional wrapper" (§17.2, §22): an
MCP server over the frozen porcelain that lets **any MCP client (non-Python hosts,
agent runtimes, Claude Desktop) drive a world with zero Python**. The porcelain
froze (`porcelain-v0.1`, additive-only), so the tool surface maps onto a stable
contract. Construct proves a *Python* host runs entirely on the porcelain; MCP
proves the contract is language-agnostic — the §1 claim demonstrated, not asserted.

## The V1 cut (Cx-confirmed right): the genuinely model-free surface
V1 exposes the deterministic surface — every read, **`ingest_structured`**, build
sessions, identity ops, `retract`. Model-backed verbs (`extract`, `ingest`-prose,
`ask`, `resolve`, `refer` tier-2) are V1.1 via MCP sampling.

**The honest subset (Cx 521 #1).** "Model-free" is a property of *parameter
domains*, not just verb choice: on a no-model `World`, `ingest_structured` with
`classify="inline"|"batch"` and `seal_build(model=True)` still *reach* the model
path (the `_no_model` sentinel fires and the classifier falls back). So the MCP
tools expose the **narrower value domains that are genuinely model-free**:

- `ingest_structured.classify ∈ {"rules", "defer"}`, **default `"rules"`** (safe:
  guardrails + STATE, zero LM).
- `seal_build` does **not** expose `model` (server always calls `model=False`).
- **Runtime validation rejects** `inline`/`batch`/`model=true` before dispatch —
  enforced in the dispatch layer, not merely described in tool docs.
- The spec claim is precise: V1 tool signatures are the frozen porcelain
  signatures **with deliberately narrower value domains where the frozen defaults
  reach the model path**. An honest protocol subset of frozen verbs, not a new
  engine surface.
- Tests install a **raising spy** as the model callable and prove every V1 tool
  makes **zero model-path calls**, plus negative tests that the rejected modes are
  refused at dispatch.

## The verb registry (Cx 521 #2): explicit and exhaustive, never reflective
An **explicit V1 registry of 37 tools** — the full deterministic surface (Cx: keep
it complete; 37 discoverable tools is the stronger membrane proof; includes
**`state_union`**, which the draft enumeration accidentally omitted):

reads: `snapshot`, `state`, `state_union`, `where`, `aggregate`, `confidence`,
`locate`, `contents`, `composition`, `features`, `path`, `route`, `neighborhood`,
`salience`, `frame_diff`, `who_knows`, `events`, `entities`, `facts`,
`fidelity_audit`, `axis_heads`, `proposals`, `correlations`,
`correlation_conflicts`, `typing_conflicts`;
writes/identity/build: `ingest_structured`, `retract`, `reconcile`,
`adjudicate_deferred`, `confirm`, `merge`, `reject`, `correlate`, `retype`,
`begin_build`, `seal_build`, `abort_build`.

- Schemas are generated from the frozen signatures **where annotations suffice**,
  with **declared overrides** where they don't (SDK 1.28.1 maps unannotated params
  to `type: string`, which is wrong for): `snapshot.scope` and `frame_diff.scope`
  (`string | array[string]`), `where.value` (JSON number **or** the exact-decimal
  tag object), plus the §above domain restrictions.
- **No automatic reflection of future porcelain methods**: a porcelain addition
  must receive a V1/V1.1 classification, annotations, and schema review before it
  can appear — the registry asserts its own completeness in tests, so an additive
  verb can neither appear accidentally nor go silently unclassified.

## The wire convention (Cx 521 #3): one mechanical envelope
MCP structured results are JSON **objects**; porcelain returns include top-level
lists, primitives, `None`, and `Receipt` dataclasses. One uniform rule:

```
structuredContent = {"result": encode_out(normalize(porcelain_return))}
```

where `normalize(Receipt) = Receipt.to_dict()` (likewise any dataclass return) and
the `result` value is the actual JSON value, never a quoted string. The same
object is serialized into a single compatibility `TextContent` block. The test
oracle is **deep equality after the declared envelope/normalization** against the
direct porcelain call — not byte-identity (which the protocol makes false). Wire
tests cover dict, list, primitive, `None`, and `Receipt` returns, with output
schemas declared to match the envelope.

## Launch, authority, and annotations (Cx 521 #4)
- **Launch surface:** `--world PATH --world-id ID` (env: `PATTERNBUFFER_WORLD`,
  `PATTERNBUFFER_WORLD_ID`); both required — `World` construction needs the id,
  and requiring it beats the adapter peeking at private SQLite metadata (membrane).
  Fresh path ⇒ a new world is created with that id; existing path with a
  mismatched id ⇒ the engine's `WorldMismatch` fails startup loudly.
- **One server ↔ one world** (the §16 1:1 invariant); multi-world = multiple
  server instances, never a multiplexer.
- **`ToolAnnotations`, exact table:** deterministic reads `readOnlyHint=true`;
  every write/build op `readOnlyHint=false`; additive writes
  `destructiveHint=false`; ops that retract, collapse identity, or supersede the
  effective view (`retract`, `merge`, `confirm`, `retype`, `adjudicate_deferred`,
  `reconcile`, `seal_build`) conservatively `destructiveHint=true`; only
  retry-safe ops `idempotentHint=true` (reads; `abort_build`; `reject`;
  `correlate`); all V1 tools `openWorldHint=false` (a bound local world is a
  closed domain). The table is tested, not aspirational.
- **The trust boundary, stated honestly:** this wrapper is a **fully trusted
  world principal** — a connected client can name any frame (`plot:*`,
  `knows:*`), and `who_knows` reveals frame ids by design. Annotations are hints,
  never authorization. Untrusted consumers (players, NPCs) go through a
  host-mediated surface; frame entitlement is and remains a host concern
  (whitepaper §17.2). The README section for the server carries this paragraph.

## Shape (unchanged from r1 where not amended above)
- Optional module `patternbuffer.mcp`, installed via `patternbuffer[mcp]` (SDK
  dependency lives in the extra; lazy import; **the dependency-free core never
  imports it** — audited by a fresh-subprocess test: base install imports
  `patternbuffer` with no `mcp` requirement).
- Transport: stdio for V1.
- **Mutation dispatch is serialized** (build-session state is server/world state,
  not per-request state); lifecycle tests cover close-after-shutdown and an open
  build session aborted by shutdown (`abort_build` semantics — classify nothing).

## Non-goals
- No model-backed verbs (V1.1, MCP sampling). No multiplexer, no auth/entitlement
  layer (trusted-principal only, stated), no non-stdio transport. No engine
  change; no reflective tool surface.

## Release
Ships as `patternbuffer 0.1.0` to PyPI with the `[mcp]` extra (founder-approved
bundling; license reconciled to MIT). The `[mcp]` wheel exposes the server entry
point (`patternbuffer-mcp`).

## Tests
- **Zero-model proof:** raising-spy model; every V1 tool dispatches with zero
  model-path calls; `classify="inline"|"batch"` and `seal_build(model=true)`
  rejected at dispatch (negative tests).
- **Registry:** exactly the declared 37 tools; completeness assertion against the
  porcelain's public no-model surface (a new porcelain verb fails the test until
  classified); schema overrides present for `scope`/`scope`/`value`.
- **Wire:** dict/list/primitive/None/Receipt round-trips deep-equal the direct
  porcelain call under the envelope; output schemas validate.
- **Annotations:** the exact hint table, asserted per tool.
- **Membrane:** fresh-subprocess import tests (base install: no `mcp` import;
  `[mcp]`: entry point present); real stdio initialize/list/call/shutdown smoke
  test against the installed SDK.
- **Lifecycle:** launch validation (missing/mismatched world-id fails loudly);
  close-after-shutdown; abort-open-build-on-shutdown; serialized mutations.
- Full engine suite green; core byte-unchanged.
