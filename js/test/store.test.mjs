import { test } from "node:test";
import assert from "node:assert/strict";
import { openView, viewKey } from "../patternbuffer/store.mjs";
import { memoryBackend } from "../patternbuffer/backend.mjs";
import { sameDocument } from "../patternbuffer/view.mjs";
import { fakeLocks, ok, tick, vectors, withNavigator } from "./helpers.mjs";

const WORLD = "w:manor";
const FRAME = "knows:person:mara";
const seq = vectors("view-feed-v1.json").sequences[0];   // keyed: every op

/** A transport that serves the sequence's answers in order and checks each body. */
function scripted(session, answers) {
  const bodies = [];
  const transport = async (body) => {
    bodies.push(structuredClone(body));
    return ok(answers[bodies.length - 1]);
  };
  return { transport, bodies };
}

const open = (backend, extra = {}) => openView({
  backend, worldId: WORLD, viewFrame: FRAME, session: "viewer", seed: seq.start, ...extra,
});

test("a view opens from its seed, syncs, persists, and reopens to the same document", async () => {
  const backend = memoryBackend();
  const view = await open(backend);
  assert.equal(view.reseeded, true);
  assert.ok(sameDocument(view.doc, seq.start));
  const { transport, bodies } = scripted("viewer", seq.steps.map((s) => s.answer));
  for (const step of seq.steps) {
    const doc = await view.sync(transport);
    assert.ok(sameDocument(doc, step.expect), step.name);
    assert.ok(sameDocument(view.doc, step.expect));
    assert.ok(sameDocument(await backend.get(viewKey(WORLD, FRAME)), step.expect));
  }
  const reopened = await open(backend, { seed: undefined });
  assert.equal(reopened.reseeded, false);
  assert.ok(sameDocument(reopened.doc, seq.steps.at(-1).expect));
  assert.equal(bodies.length, seq.steps.length);
});

test("each feed body is exactly {session, verb, args: {since}}, since absent on a null cursor", async () => {
  const backend = memoryBackend();
  const view = await open(backend, { session: "photonic-view", seed: undefined });
  assert.equal(view.doc.cursor, null);
  const { transport, bodies } = scripted("photonic-view", seq.steps.map((s) => s.answer));
  await view.sync(transport);
  await view.sync(transport);
  assert.deepEqual(bodies[0], { session: "photonic-view", verb: "feed", args: {} });
  assert.ok(!("since" in bodies[0].args));
  assert.deepEqual(bodies[1], {
    session: "photonic-view", verb: "feed", args: { since: seq.steps[0].answer.cursor },
  });
  assert.deepEqual(Object.keys(bodies[1]).sort(), ["args", "session", "verb"]);
});

test("without a seed the view starts from the empty document", async () => {
  const view = await openView({ backend: memoryBackend(), worldId: WORLD, viewFrame: FRAME, session: "v" });
  assert.deepEqual(view.doc, {
    schema: "patternbuffer.view/1", world_id: WORLD, view_frame: FRAME,
    at: null, cursor: null, known: {}, present: null,
  });
});

test("a throwing apply leaves the persisted document unchanged and rejects", async () => {
  const backend = memoryBackend();
  const view = await open(backend);
  await view.sync(scripted("viewer", [seq.steps[0].answer]).transport);
  const before = await backend.get(viewKey(WORLD, FRAME));
  const bad = { cursor: "x", at: 9, present_on: true, ops: [{ op: "frob" }] };
  await assert.rejects(view.sync(async () => ok(bad)), { message: "unknown op 'frob'" });
  assert.deepEqual(await backend.get(viewKey(WORLD, FRAME)), before);
  assert.deepEqual(view.doc, before);
  // present_on mismatch without a clear
  const mismatch = { cursor: "x", at: 9, present_on: false, ops: [] };   // the document is keyed
  await assert.rejects(view.sync(async () => ok(mismatch)), /present_on/);
  assert.deepEqual(await backend.get(viewKey(WORLD, FRAME)), before);
});

test("a failed call or a non-result answer rejects and changes nothing", async () => {
  const backend = memoryBackend();
  const view = await open(backend);
  const before = structuredClone(view.doc);
  await assert.rejects(view.sync(async () => { throw new Error("offline"); }), { message: "offline" });
  await assert.rejects(view.sync(async () => ({ status: 400, json: { error: { type: "refused", message: "nope" } } })),
    /HTTP 400: refused: nope/);
  await assert.rejects(view.sync(async () => ({ status: 200, json: null })), /sync: HTTP 200/);
  await assert.rejects(view.sync(async () => ({ status: 504, json: null })), /HTTP 504/);
  assert.deepEqual(view.doc, before);
  assert.deepEqual(await backend.get(viewKey(WORLD, FRAME)), before);
});

test("two concurrent syncs run one after the other", async () => {
  const backend = memoryBackend();
  const view = await open(backend);
  let inFlight = 0;
  let overlapped = false;
  const bodies = [];
  const transport = async (body) => {
    bodies.push(structuredClone(body));
    inFlight += 1;
    if (inFlight > 1) overlapped = true;
    await tick(5);
    inFlight -= 1;
    return ok(seq.steps[bodies.length - 1].answer);
  };
  const [a, b] = await Promise.all([view.sync(transport), view.sync(transport)]);
  assert.equal(overlapped, false);
  assert.ok(sameDocument(a, seq.steps[0].expect));
  assert.ok(sameDocument(b, seq.steps[1].expect));
  assert.deepEqual(bodies[1].args, { since: seq.steps[0].answer.cursor });
});

test("replace persists a fresh export", async () => {
  const backend = memoryBackend();
  const view = await open(backend);
  const fresh = seq.steps[2].expect;
  await view.replace(fresh);
  assert.ok(sameDocument(view.doc, fresh));
  assert.ok(sameDocument(await backend.get(viewKey(WORLD, FRAME)), fresh));
  fresh.known = {};                    // the caller's object is not shared
  assert.ok(!sameDocument(view.doc, fresh));
  await assert.rejects(async () => view.replace("not a document"), TypeError);
});

test("persisted reflects navigator.storage.persist(), null without it", async () => {
  assert.equal((await open(memoryBackend())).persisted, null);
  await withNavigator({ storage: { persist: async () => true } }, async () => {
    assert.equal((await open(memoryBackend())).persisted, true);
  });
  await withNavigator({ storage: { persist: async () => false } }, async () => {
    assert.equal((await open(memoryBackend())).persisted, false);
  });
});

test("the key is encoded per part, so a colon cannot collide", () => {
  assert.equal(viewKey("w:manor", "knows:person:mara"), "pb:view:w%3Amanor:knows%3Aperson%3Amara");
  assert.notEqual(viewKey("a:b", "c"), viewKey("a", "b:c"));
});

// test 3a
test("with a fake navigator.locks, two views on one key sync one after the other", async () => {
  const locks = fakeLocks();
  await withNavigator({ locks }, async () => {
    const backend = memoryBackend();
    const tabA = await open(backend);
    const tabB = await open(backend);
    let inFlight = 0;
    let overlapped = false;
    const bodies = [];
    const transport = async (body) => {
      bodies.push(structuredClone(body));
      inFlight += 1;
      if (inFlight > 1) overlapped = true;
      await tick(5);
      inFlight -= 1;
      return ok(seq.steps[bodies.length - 1].answer);
    };
    const [a, b] = await Promise.all([tabA.sync(transport), tabB.sync(transport)]);
    assert.equal(overlapped, false);
    assert.equal(locks.maxHeld, 1);
    assert.ok(locks.names.includes(viewKey(WORLD, FRAME)));
    assert.deepEqual(bodies[0].args, {});
    // the second carries on from the first's cursor and does not overwrite it
    assert.deepEqual(bodies[1].args, { since: seq.steps[0].answer.cursor });
    assert.ok(sameDocument(a, seq.steps[0].expect));
    assert.ok(sameDocument(b, seq.steps[1].expect));
    assert.ok(sameDocument(await backend.get(viewKey(WORLD, FRAME)), seq.steps[1].expect));
    // tab A still shows its own sync until it syncs again, which carries on from the store
    assert.ok(sameDocument(tabA.doc, seq.steps[0].expect));
  });
});

test("reseeded is true on a first open and false on a reopen", async () => {
  const backend = memoryBackend();
  assert.equal((await open(backend)).reseeded, true);
  assert.equal((await open(backend)).reseeded, false);
  // storage evicted: the seed loads again and says so
  await backend.del(viewKey(WORLD, FRAME));
  const again = await open(backend);
  assert.equal(again.reseeded, true);
  assert.ok(sameDocument(again.doc, seq.start));
});

test("openView refuses a missing backend, session or frame", async () => {
  const base = { backend: memoryBackend(), worldId: WORLD, viewFrame: FRAME, session: "s" };
  await assert.rejects(openView({ ...base, backend: {} }), TypeError);
  await assert.rejects(openView({ ...base, session: "" }), TypeError);
  await assert.rejects(openView({ ...base, viewFrame: undefined }), TypeError);
  await assert.rejects(openView({ ...base, worldId: 3 }), TypeError);
});
