# RESOLVE-REQUEST-V1: a resolve call carries its purpose as data

**Status:** r1, spec + build together for pbr. Author: pb, 2026-10-12. Roadmap R37 (E2 of
`specs/proposals/UNIFIED-WORLD-ACCESS.md`, approved by Kabe on 2026-10-12, gate gde97f3).

## Need

The agreed structure is code first, with the model as one route. A code generator (Photonic's seeded
sampler for people, holo-emitter's room generators) answers a `patternbuffer_resolve` call. Today the
call's purpose (which entity, which aspect, under which constraints) exists only as prompt prose, and
prompt wording is not a contract. A code generator would have to parse sentences.

## Rule

1. Every `patternbuffer_resolve` call carries a **`ResolveRequest`** (frozen dataclass, exported):

   | Field | Meaning |
   |---|---|
   | `world_id` | the world |
   | `entity` | the placeholder's subject |
   | `aspect` | its attribute |
   | `kind` | the entity's folded `kind`, or None |
   | `inherited` | `((holder, attribute, value), …)`: the standing facts the resolver inherits (whitepaper §8) |
   | `declared` | the placeholder's own constraint strings |
   | `as_of` | the placeholder's `valid_from` |
   | `frame` | the frame |
   | `policy` | the policy |

   `inherited` followed by `declared` is exactly the prompt's constraint list, in the same order. So
   the prompt and the request never disagree.

2. **Transport: the schema object itself.** The engine hands the callable a `TaskSchema`, a `dict`
   subclass with the same keys and values that also holds `.request`.
   - It serializes byte-identically, so every adapter that forwards the schema to a model (strict-mode
     rewrites included) sends exactly what it sent before.
   - A generator reads the request with `task_request(schema)`, which returns the `ResolveRequest`,
     or None on every other call and on a schema an adapter rebuilt.
   - The callable's signature `(prompt, schema) -> json` is unchanged. It remains the engine's single
     outside dependency.

3. **Considered and rejected:**
   - A new schema keyword (`x-patternbuffer-request`): strict structured-output APIs can reject
     unknown keywords, and every host forwards the schema.
   - A second injected callable: this would break the single-dependency rule.
   - A frozen machine-readable block in the prompt: this makes prompt text a contract.

## What does not change

- The prompt is byte-identical.
- The schema's JSON is byte-identical.
- Every other task's schema stays a plain `dict` copy.
- No row is written differently.

## Checks

`tests/test_resolve_request.py`:
- the request's fields;
- request = prompt lines;
- byte-identical JSON;
- other tasks carry none;
- a code generator answers from the request, memoized;
- deep copies keep the request, and rebuilds drop it.

Plus the full suite.

## V1.1: `current`, the entity's own state now (2026-10-12)

**Need (Photonic, m6b231f and m956978).** A code generator reads the story's facts about a person
through `inherited`, which carries CONSTITUTIVE and DISPOSITIONAL facts only (whitepaper §8). Age is
STATE by doctrine, since it is true at the cursor, and so is a description that can change, such as
a haircut. So neither reaches the generator. Pinning them DISPOSITIONAL would be wrong, because a
time skip would leave a 30-year-old at 30.

**Rule.** `ResolveRequest` gains a last field, `current: tuple[tuple[str, Any], ...] = ()`:
- **What it holds:** the entity's **own** folded facts whose served row is STATE, as of the
  placeholder's `valid_from` (at head for a timeless placeholder), as `(attribute, value)` sorted by
  attribute.
- **What it excludes:** ancestors and placeholders. The aspect being forced is always excluded,
  because its fold winner is its own placeholder.
- **Accrue keys:** an accrue key gives its running total.
- **Code generators only:** the prompt is byte-identical, and the existing fields don't change.
- **Not added:** ancestors' state (lighting, weather) is render-side, and Photonic doesn't need it.

**Checks.** `tests/test_resolve_request_current.py`:
- `current` holds the entity's own state as of the placeholder's time, which a later change does
  not affect;
- a later placeholder sees the later value;
- DISPOSITIONAL facts stay in `inherited` and never appear in `current`;
- an ancestor's state never appears;
- the prompt is unchanged.

