import { test } from "node:test";
import assert from "node:assert/strict";
import { idbBackend } from "../patternbuffer/idb.mjs";
import { openView } from "../patternbuffer/store.mjs";
import { openQueue } from "../patternbuffer/queue.mjs";

// test 6: runs only where an indexedDB exists (a browser, or node with a polyfill);
// Photonic's Safari check is the real test
const reason = "no global indexedDB in this runtime; the Safari check is the real test";
const skip = typeof globalThis.indexedDB === "undefined" ? reason : false;

test("idbBackend follows the backend contract", { skip }, async () => {
  const backend = idbBackend(`pb-test-${Date.now()}-${Math.random()}`);
  assert.equal(await backend.get("missing"), undefined);
  const value = { a: [1, { b: null }], c: "d" };
  await backend.put("k", value);
  const got = await backend.get("k");
  assert.deepEqual(got, value);
  assert.notEqual(got, value);                       // structured-cloned, not shared
  await backend.put("k", { replaced: true });
  assert.deepEqual(await backend.get("k"), { replaced: true });
  await backend.del("k");
  assert.equal(await backend.get("k"), undefined);
  await backend.del("k");                            // deleting what is absent is fine
});

test("a view and a queue run over idbBackend", { skip }, async () => {
  const backend = idbBackend(`pb-test-${Date.now()}-${Math.random()}`);
  const view = await openView({ backend, worldId: "w", viewFrame: "knows:person:a", session: "v" });
  assert.equal(view.reseeded, true);
  assert.equal((await openView({ backend, worldId: "w", viewFrame: "knows:person:a", session: "v" })).reseeded, false);
  const q = await openQueue({ backend, worldId: "w", session: "s", role: "recorder" });
  await q.add([{ entity: "person:a", attribute: "posture", value: "sitting" }]);
  assert.equal((await q.pending()).length, 1);
});

test("idbBackend without an indexedDB rejects with a clear error", { skip: skip ? false : "indexedDB exists here" }, async () => {
  await assert.rejects(idbBackend("x").get("k"), /indexedDB is not available/);
});
