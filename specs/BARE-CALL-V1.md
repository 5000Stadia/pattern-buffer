# BARE-CALL-V1: every build model call is one bare call

**Status:** r1, for pbr review. Author: pb, 2026-10-13. Harness only.
**Source:** consult c4bb1f2, point 1, accepted by Kabe on gate g936be9 (2026-10-13). Kabe also
said yes to a 2-chapter profiling build on the practice book once this is merged. The point:
"Each 'model call' is a whole Claude Code agent session … the 176–282 s pass-0 calls and the
parallel slowdown may be harness overhead … Make each request one bare call: one turn, no tools,
run from an empty directory with no settings or memory."

## Need

`evals/harness/model_shim.py` runs `claude -p --model M --max-turns 8 --output-format json`, with
the prompt on stdin. It sets no other flags and no working directory. So every extraction,
classification, gate and audit call:
- **loads Claude Code's full default system prompt and tool definitions,** then auto-discovers
  `CLAUDE.md` and the project's memory, because it inherits the caller's working directory (this
  repo);
- **may take up to 8 turns and use file tools.** Those tools run in the repo that holds every
  book's `key.json`. No evidence shows any call did; turns were not logged before
  BUILD-PROFILE-V1;
- **pays for all of that in latency and input tokens,** which no receipt separated from the work.

That makes each measurement before this spec unclear about how much is harness overhead, and
leaves the answer keys reachable in principle.

## The shape

`claude_model(prompt, schema)` makes exactly this call:

```
claude -p --model M --output-format json
       --max-turns 1
       --tools ""
       --strict-mcp-config
       --setting-sources ""
       --no-session-persistence
       --system-prompt <BARE_SYSTEM_PROMPT>
```

The prompt still goes on stdin.
- **Working directory:** a fresh, empty temporary directory, made per call
  (`tempfile.TemporaryDirectory`) and removed after it.
  - No `CLAUDE.md`, project memory or repo file is in reach. The project memory path is keyed by
    the working directory, so an empty temporary directory has none.
  - The environment is inherited, so authentication (OAuth) still works. `--bare` is not used
    because it refuses OAuth.
- **`BARE_SYSTEM_PROMPT`** is a short, fixed module constant: "You answer with one JSON object
  that matches the schema in the user message. No prose, no code fences, no tools." It replaces
  Claude Code's default system prompt.
- **`--setting-sources ""`** loads no user, project or local settings, so no hooks and no plugins.
  Managed settings, if any, still apply, as the CLI documents.
- **Everything else is unchanged:**
  - the retry loop: three attempts, back-off, and a JSON-repair re-prompt;
  - the quota detection;
  - the timeout;
  - the receipts and the profile fields.
- **Turns are checked on every call.** A result envelope reporting `num_turns > 1` is logged at
  `WARNING`, and its call line gets `outcome: "multi_turn"`. It is counted, never silently
  accepted.
- **The shim exposes its argv** as one function, `bare_argv(model) -> list[str]`, so the test can
  assert it without running `claude`.
- `PB_SHIM_LEGACY=1` restores the old command line, for one comparison run if ever wanted. The
  default is bare, and the variable is documented as temporary.

## The smoke test (paid, one call, a few hundred tokens)

`python -m evals.harness.model_shim --smoke` makes one bare call with a two-line prompt and a
one-field schema. It prints the result envelope's `num_turns`, `duration_api_ms`, `duration_ms`,
input and output tokens, and whether any tool use was reported. It is run once by hand after the
merge (covered by Kabe's yes on the profiling build). Its output goes into the profiling report.

## Not in this spec

- Any change to prompts, schemas or the pipeline.
- `codex_shim`, which already makes one HTTP request per call and runs no agent loop.
- The profiling build itself. It is run under BUILD-PROFILE-V1 after this merges.

## Tests (no model calls)

1. `bare_argv(M)` equals the command line above exactly, and contains no `--max-turns 8`.
2. With `subprocess.run` patched, a `claude_model` call:
   - passes `cwd` as a directory that exists during the call and is empty;
   - removes that directory afterwards, on success and on failure;
   - passes the prompt on stdin.
3. A patched envelope with `num_turns: 3` returns its JSON, logs a warning, and writes a call line
   with `outcome: "multi_turn"`. An envelope with `num_turns: 1` gives `"ok"`.
4. `PB_SHIM_LEGACY=1` gives the old argv and no `cwd`.
5. The retry, quota and timeout paths behave as before, and `tests/test_usage_ledger.py` and
   `tests/test_build_profile.py` pass unchanged.
6. The full suite is green.
