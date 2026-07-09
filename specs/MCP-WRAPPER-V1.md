# MCP-WRAPPER-V1 — the porcelain over MCP: the engine-independence proof, non-Python

**Status:** DRAFT → Cx review. The whitepaper's reserved "later optional wrapper"
(§17.2, §22): an MCP server over the frozen porcelain that lets **any MCP client
(non-Python hosts, agent runtimes, Claude Desktop) drive a world with zero Python**.
The porcelain froze (`porcelain-v0.1`, additive-only), so the tool schema maps 1:1
onto a stable surface and won't churn — this is the timing the whitepaper reserved.
Construct proves a *Python* host runs entirely on the porcelain; MCP proves the
contract is language-agnostic — the §1 claim demonstrated, not asserted.

## The one design decision, resolved by scoping (not deferred blindly)
The porcelain splits cleanly:
- **No-model surface** (the majority): every read (`snapshot`/`state`/`where`/
  `aggregate`/`confidence`/`locate`/`contents`/`composition`/`features`/`path`/
  `route`/`neighborhood`/`salience`/`frame_diff`/`who_knows`/`events`/`entities`/
  `facts`/`fidelity_audit`/`axis_heads`/`proposals`/`correlations`/
  `correlation_conflicts`/`typing_conflicts`), the **structured write**
  `ingest_structured`, the **build lifecycle** (`begin_build`/`seal_build`/
  `abort_build`), the **identity ops** (`reconcile`/`adjudicate_deferred`/`confirm`/
  `merge`/`reject`/`correlate`/`retype`), and `retract`. None call a model.
- **Model-backed surface** (the minority): `extract`, `ingest` (prose→log), `ask`,
  `resolve` (thunk invention/observation), `refer` tier-2. These need `(prompt,
  schema)->json`.

**V1 exposes the no-model surface, full stop.** The server constructs its `World`
with **no model callable** (none is reachable), so the model-seam question does not
arise — and the claim is still fully proven: a non-Python client can **read, query,
and BUILD** a world (structured writes + build sessions + identity) end to end. The
model-backed verbs are **V1.1 via MCP sampling** (the client's model does
extraction — membrane-honest: the host still supplies the model, now over the
protocol). Shipping V1 first delivers the proof immediately without betting on the
sampling design.

## Shape
- **An optional module `patternbuffer.mcp`**, installed via `pip install
  patternbuffer[mcp]` (a new optional-dependency group pulling the `mcp` SDK). The
  **engine core stays dependency-free** — `patternbuffer.mcp` imports the SDK lazily
  and is never imported by the core (audited, mirroring the porcelain lazy-import
  discipline). No core file gains an import.
- **One server ↔ one world** — the 1:1 invariant (§16) is the natural server unit: a
  world *is* a file. The server launches bound to a world path (arg/env); it opens
  the `World` once (no model), serves it, closes on shutdown. Multi-world is multiple
  server instances, not a multiplexer (keeps the invariant structural, not policed).
- **Tools are the porcelain verbs, schema-generated from the frozen signatures.**
  Each no-model verb becomes one MCP tool; params map to a JSON-schema input; the
  return dict/list is the tool result (already `encode_out`-wrapped → plain-JSON,
  decimal-safe). The wrapper is **thin**: schema + dispatch + JSON — it calls
  `world.porcelain.<verb>` only, never engine internals, and adds **no engine
  surface** (membrane; it is an adapter, like a host, but ships in-repo as the
  framework-agnostic demo per §17.2).
- **Tool safety annotations:** reads carry `readOnlyHint`; `ingest_structured`,
  identity ops, `retract`, and the build verbs carry the mutation/`destructiveHint`
  hints so a client surfaces write intent. Frame-scoping is unchanged — a client
  reads only frames it names (the §6 absence discipline rides through untouched;
  the server adds no entitlement policy of its own — that stays a host concern).
- **Transport:** stdio (the MCP default) for V1; nothing precludes others later.

## Non-goals
- **No model-backed verbs in V1** (`ingest`-prose/`ask`/`resolve`/`refer`/`extract`)
  — V1.1 via sampling; V1's `World` has no model.
- **No multi-world multiplexer, no auth/session model, no non-stdio transport** —
  each is additive when a real client needs it.
- **No engine change.** The wrapper is pure adapter over the frozen porcelain; if a
  verb is awkward over MCP that is a porcelain question, not an MCP one.
- No change to the dependency-free core; `mcp` is strictly an optional extra.

## Open items (flag for Cx / founder)
- **SDK availability.** Implementation needs the `mcp` Python SDK installable in the
  build env; if absent in the sandbox, the module + its schema-generation ship and
  unit-test against a stub MCP shim, with live-client verification deferred. (Spec is
  design-complete regardless.)
- **License mismatch (out of scope, noted):** `pyproject.toml` says `Proprietary`;
  `README`/`LICENSE` say MIT. Worth reconciling before any PyPI publish — not part of
  this spec.

## Tests
- Schema generation: every no-model porcelain verb yields a valid MCP tool with an
  input schema matching its signature (params, defaults, types); the model-backed
  verbs are absent from V1's tool list.
- Dispatch round-trip (against a stub MCP shim / direct call): `entities`, `snapshot`,
  `state`, `fidelity_audit`, `ingest_structured`, a build session, and an identity op
  each execute through the tool layer and return the same payload as the direct
  porcelain call (byte-identical, plain-JSON).
- The core remains import-clean: importing `patternbuffer` pulls no `mcp`; the core
  package has zero third-party imports (audited by test).
- Read tools carry `readOnlyHint`; write/identity/build tools carry the mutation hint.
- Full suite green; the engine core is byte-unchanged.
