import { test } from "node:test";
import assert from "node:assert/strict";
import { openQueue, queueKey } from "../patternbuffer/queue.mjs";
import { memoryBackend } from "../patternbuffer/backend.mjs";
import { fakeLocks, tick, withNavigator } from "./helpers.mjs";

const ITEM = { entity: "person:cook", attribute: "posture", value: "sitting", valid_from: 1 };
const item = (n) => ({ entity: `person:p${n}`, attribute: "posture", value: `v${n}`, valid_from: n });
const REC = { status: 200, json: { result: { status: "recorded" } } };
const REF = { status: 200, json: { result: { status: "refused" } } };

const open = (backend, extra = {}) => openQueue({
  backend, worldId: "w:one", session: "holo", role: "recorder", ...extra,
});

/** A transport that answers from a list (a function entry may throw) and logs bodies. */
function serving(answers) {
  const bodies = [];
  const transport = async (body) => {
    bodies.push(structuredClone(body));
    const next = answers[Math.min(bodies.length - 1, answers.length - 1)];
    return typeof next === "function" ? next() : next;
  };
  return { transport, bodies };
}

test("calls flush in order, and recorded drops them", async () => {
  const q = await open(memoryBackend());
  await q.add([item(1)], { at: 5 });
  await q.add([item(2)]);
  await q.add([item(3)], { at: 7 });
  assert.equal((await q.pending()).length, 3);
  const { transport, bodies } = serving([REC]);
  assert.equal(await q.flush(transport), 3);
  assert.deepEqual(bodies.map((b) => b.args.items[0].entity), ["person:p1", "person:p2", "person:p3"]);
  assert.deepEqual(bodies[0], { session: "holo", verb: "record", args: { items: [item(1)], at: 5 } });
  assert.deepEqual(bodies[1].args, { items: [item(2)] });          // no at, no frame unless given
  assert.deepEqual(await q.pending(), []);
  assert.equal(await q.flush(transport), 0);
});

test("refused and a 400 drop the call and call onRefused with it", async () => {
  const refused = [];
  const q = await open(memoryBackend(), { onRefused: (call) => refused.push(call) });
  await q.add([item(1)]);
  await q.add([item(2)]);
  await q.add([item(3)]);
  const { transport } = serving([REF, { status: 400, json: { error: { type: "refused", message: "x" } } }, REC]);
  assert.equal(await q.flush(transport), 3);
  assert.deepEqual(refused, [
    { verb: "record", args: { items: [item(1)] } },
    { verb: "record", args: { items: [item(2)] } },
  ]);
  assert.deepEqual(await q.pending(), []);
});

test("without onRefused a refusal is logged with console.warn", async () => {
  const q = await open(memoryBackend());
  await q.add([item(1)]);
  const warned = [];
  const original = console.warn;
  console.warn = (...args) => warned.push(args);
  try {
    await q.flush(serving([REF]).transport);
  } finally {
    console.warn = original;
  }
  assert.equal(warned.length, 1);
  assert.deepEqual(await q.pending(), []);
});

test("a throwing onRefused does not lose the rest of the flush", async () => {
  const q = await open(memoryBackend(), { onRefused: () => { throw new Error("ui broke"); } });
  await q.add([item(1)]);
  await q.add([item(2)]);
  const original = console.error;
  console.error = () => {};
  try {
    assert.equal(await q.flush(serving([REF, REC]).transport), 2);
  } finally {
    console.error = original;
  }
  assert.deepEqual(await q.pending(), []);
});

for (const [name, failure] of [
  ["a transport error", () => { throw new TypeError("fetch failed"); }],
  ["a 500", { status: 500, json: { error: { type: "Boom", message: "see the service log" } } }],
  ["a 504", { status: 504, json: { error: { type: "timeout", message: "t" } } }],
  ["a 404", { status: 404, json: null }],
  ["a 200 this module does not understand", { status: 200, json: { result: { status: "deferred" } } }],
]) {
  test(`${name} stops the flush, keeps the rest, and a reopened queue still holds them`, async () => {
    const backend = memoryBackend();
    const q = await open(backend);
    for (const n of [1, 2, 3, 4]) await q.add([item(n)]);
    const { transport, bodies } = serving([REC, failure]);
    assert.equal(await q.flush(transport), 1);
    assert.equal(bodies.length, 2);                       // it stopped at the failure
    const reopened = await open(backend);
    const waiting = await reopened.pending();
    assert.deepEqual(waiting.map((c) => c.args.items[0].entity), ["person:p2", "person:p3", "person:p4"]);
    // the next flush resumes with the kept call
    const second = serving([REC]);
    assert.equal(await reopened.flush(second.transport), 3);
    assert.equal(second.bodies[0].args.items[0].entity, "person:p2");
  });
}

test("add refuses a delta item, an item frame, an item status and an unknown key", async () => {
  const q = await open(memoryBackend());
  await assert.rejects(q.add([{ ...ITEM, value_type: "delta", value: 5 }]), /delta/);
  await assert.rejects(q.add([{ ...ITEM, frame: "canon" }]), /frame\/status/);
  await assert.rejects(q.add([{ ...ITEM, status: "stated" }]), /frame\/status/);
  await assert.rejects(q.add([{ ...ITEM, aliases: ["x"] }]), /keys a play event may not: aliases/);
  await assert.rejects(q.add([]), TypeError);
  await assert.rejects(q.add("nope"), TypeError);
  await assert.rejects(q.add([5]), TypeError);
  await assert.rejects(q.add([{ attribute: "a", value: 1 }]), TypeError);
  await assert.rejects(q.add([{ ...ITEM, value_type: "unresolved" }]), TypeError);
  await assert.rejects(q.add([ITEM], { at: "now" }), TypeError);
  await assert.rejects(q.add([ITEM], { at: NaN }), TypeError);
  await assert.rejects(q.add([ITEM], { att: 1 }), /unknown option/);
  assert.deepEqual(await q.pending(), []);
  // the allowed keys are accepted
  await q.add([{ ...ITEM, value_type: "literal", valid_from: 1, valid_to: 2, timeless: false },
    { entity: "person:cook", attribute: "in", value: "place:hall", value_type: "entity",
      valid_from: 1 }]);
  assert.equal((await q.pending()).length, 1);
});

test("a call is stored as plain JSON and not shared with the caller", async () => {
  const q = await open(memoryBackend());
  const items = [{ ...ITEM }];
  await q.add(items);
  items[0].value = "changed";
  assert.equal((await q.pending())[0].args.items[0].value, "sitting");
  const copy = await q.pending();
  copy.length = 0;
  assert.equal((await q.pending()).length, 1);
});

test("persisted reflects navigator.storage.persist(), null without it", async () => {
  assert.equal((await open(memoryBackend())).persisted, null);
  await withNavigator({ storage: { persist: async () => true } }, async () => {
    assert.equal((await open(memoryBackend())).persisted, true);
  });
  await withNavigator({ storage: { persist: async () => false } }, async () => {
    assert.equal((await open(memoryBackend())).persisted, false);
  });
  await withNavigator({ storage: { persist: async () => { throw new Error("denied"); } } }, async () => {
    assert.equal((await open(memoryBackend())).persisted, false);
  });
});

test("two worlds with one session name keep separate queues and locks", async () => {
  const locks = fakeLocks();
  await withNavigator({ locks }, async () => {
    const backend = memoryBackend();
    const one = await openQueue({ backend, worldId: "w:one", session: "author", role: "author" });
    const two = await openQueue({ backend, worldId: "w:two", session: "author", role: "author" });
    await one.add([item(1)]);
    await two.add([item(2)]);
    await two.add([item(3)]);
    assert.equal((await one.pending()).length, 1);
    assert.equal((await two.pending()).length, 2);
    const sentOne = serving([REC]);
    assert.equal(await one.flush(sentOne.transport), 1);
    assert.deepEqual(sentOne.bodies.map((b) => b.args.items[0].entity), ["person:p1"]);
    const sentTwo = serving([REC]);
    assert.equal(await two.flush(sentTwo.transport), 2);
    assert.deepEqual(sentTwo.bodies.map((b) => b.args.items[0].entity), ["person:p2", "person:p3"]);
    assert.ok(locks.names.includes(queueKey("w:one", "author")));
    assert.ok(locks.names.includes(queueKey("w:two", "author")));
    assert.notEqual(queueKey("w:one", "author"), queueKey("w:two", "author"));
  });
  // a colon in a world id does not collide
  assert.notEqual(queueKey("a:b", "c"), queueKey("a", "b:c"));
  const backend = memoryBackend();
  const x = await openQueue({ backend, worldId: "a:b", session: "c", role: "recorder" });
  const y = await openQueue({ backend, worldId: "a", session: "b:c", role: "recorder" });
  await x.add([item(1)]);
  assert.equal((await y.pending()).length, 0);
  assert.equal(queueKey("w:one", "author"), "pb:queue:w%3Aone:author");
});

test("a recorder cannot name a frame; an author may, canon or a whole knows: id", async () => {
  const recorder = await open(memoryBackend());
  await assert.rejects(recorder.add([ITEM], { frame: "canon" }), /recorder/);
  await assert.rejects(recorder.add([ITEM], { frame: "knows:person:bram" }), /recorder/);
  const backend = memoryBackend();
  const author = await openQueue({ backend, worldId: "w", session: "photonic", role: "author" });
  await author.add([ITEM], { frame: "knows:person:bram", at: 3 });
  await author.add([ITEM], { frame: "canon" });
  await author.add([ITEM]);
  for (const frame of ["knows:", "plot:x", "Canon", "knows:Person:bram", "knows:person bram", "", 5, "knows:3x"]) {
    await assert.rejects(author.add([ITEM], { frame }), TypeError, JSON.stringify(frame));
  }
  const { transport, bodies } = serving([REC]);
  await author.flush(transport);
  assert.deepEqual(bodies[0].args, { items: [ITEM], at: 3, frame: "knows:person:bram" });
  assert.deepEqual(bodies[1].args, { items: [ITEM], frame: "canon" });
  assert.deepEqual(bodies[2].args, { items: [ITEM] });
  assert.equal(bodies[0].session, "photonic");
});

test("a missing or unknown role throws at openQueue", async () => {
  const base = { backend: memoryBackend(), worldId: "w", session: "s" };
  await assert.rejects(openQueue(base), TypeError);
  await assert.rejects(openQueue({ ...base, role: "viewer" }), TypeError);
  await assert.rejects(openQueue({ ...base, role: "Author" }), TypeError);
  await assert.rejects(openQueue({ ...base, role: "author", session: "" }), TypeError);
  await assert.rejects(openQueue({ ...base, role: "author", onRefused: "x" }), TypeError);
});

test("two flushes (two tabs) never send one call twice", async () => {
  for (const locks of [fakeLocks(), undefined]) {       // the browser's lock, then the fallback chain
    await withNavigator(locks ? { locks } : {}, async () => {
      const backend = memoryBackend();
      const tabA = await open(backend);
      const tabB = await open(backend);
      for (const n of [1, 2, 3]) await tabA.add([item(n)]);
      const sent = [];
      const transport = async (body) => {
        sent.push(body.args.items[0].entity);
        await tick(3);
        return REC;
      };
      const [a, b] = await Promise.all([tabA.flush(transport), tabB.flush(transport)]);
      assert.deepEqual(sent, ["person:p1", "person:p2", "person:p3"]);
      assert.equal(a + b, 3);
      assert.deepEqual(await tabA.pending(), []);
    });
  }
});

test("an add during a flush is kept, and does not wait for the network", async () => {
  for (const locks of [fakeLocks(), undefined]) {
    await withNavigator(locks ? { locks } : {}, async () => {
      const q = await open(memoryBackend());
      await q.add([item(1)]);
      let release;
      const gate = new Promise((resolve) => { release = resolve; });
      const sent = [];
      const slow = async (body) => {
        sent.push(body.args.items[0].entity);
        await gate;
        return REC;
      };
      const flushing = q.flush(slow);
      await tick(10);
      await q.add([item(2)]);                      // returns while the first call is in flight
      assert.equal((await q.pending()).length, 2);
      release();
      assert.equal(await flushing, 2);             // the flush picks up the late add
      assert.deepEqual(sent, ["person:p1", "person:p2"]);
      assert.deepEqual(await q.pending(), []);
    });
  }
});

test("a call is dropped only after its answer: a lost answer is sent again", async () => {
  const backend = memoryBackend();
  const q = await open(backend);
  await q.add([item(1)]);
  const lost = async () => { throw new Error("connection reset"); };
  assert.equal(await q.flush(lost), 0);
  assert.equal((await (await open(backend)).pending()).length, 1);
  assert.equal(await q.flush(serving([REC]).transport), 1);
});

test("the queue never touches a document", async () => {
  const backend = memoryBackend();
  const q = await open(backend);
  await q.add([ITEM]);
  assert.deepEqual(Object.keys(await Promise.resolve(q)).sort(), ["add", "flush", "pending", "persisted"]);
});

test("a timed item with no time of its own is refused, so a retry repeats the same call", async () => {
  const q = await open(memoryBackend());
  const bare = { entity: "person:cook", attribute: "in", value: "place:hall", value_type: "entity" };
  await assert.rejects(q.add([bare]), /carries no time/);
  // the interval case: an end but no start
  await assert.rejects(q.add([{ ...bare, valid_to: 9 }]), /carries no time/);
  await assert.rejects(q.add([{ ...bare, timeless: false }]), /carries no time/);
  // a time of its own, a call-wide at, or a timeless fact is accepted
  await q.add([{ ...bare, valid_from: 4 }]);
  await q.add([bare], { at: 5 });
  await q.add([{ ...bare, valid_to: 9 }], { at: 6 });
  await q.add([{ entity: "person:cook", attribute: "eyes", value: "grey", timeless: true }]);
  assert.equal((await q.pending()).length, 4);
});

test("after a lost answer the retry sends a byte-identical body", async () => {
  const backend = memoryBackend();
  const q = await open(backend);
  const bare = { entity: "person:cook", attribute: "in", value: "place:hall", value_type: "entity" };
  await q.add([bare], { at: 5 });
  await q.add([{ ...bare, valid_to: 9 }], { at: 6 });
  const bodies = [];
  const lost = async (body) => { bodies.push(JSON.stringify(body)); throw new Error("reset"); };
  assert.equal(await q.flush(lost), 0);
  const ok = async (body) => { bodies.push(JSON.stringify(body)); return REC; };
  assert.equal(await (await open(backend)).flush(ok), 2);
  assert.equal(bodies.length, 3);
  assert.equal(bodies[0], bodies[1]);                 // the first call, sent twice, unchanged
  assert.match(bodies[0], /"at":5/);
  assert.match(bodies[2], /"at":6/);
});
