import { test } from "node:test";
import assert from "node:assert/strict";
import { apply, sameDocument, known, present, people, emptyDocument } from "../patternbuffer/view.mjs";
import { vectors } from "./helpers.mjs";

for (const file of ["view-feed-v1.json", "view-feed-people-v1.json"]) {
  const suite = vectors(file);
  for (const sequence of suite.sequences) {
    // test 1: replay every sequence, compare after every step
    test(`vectors ${file}: ${sequence.name}`, () => {
      let doc = sequence.start;
      for (const step of sequence.steps) {
        doc = apply(doc, step.answer);
        assert.ok(sameDocument(doc, step.expect), `${step.name}: document differs from expect`);
        assert.deepEqual(doc, step.expect);
      }
    });
    // test 2: purity
    test(`purity ${file}: ${sequence.name}`, () => {
      let doc = sequence.start;
      for (const step of sequence.steps) {
        const docBefore = structuredClone(doc);
        const answerBefore = structuredClone(step.answer);
        const next = apply(doc, step.answer);
        assert.deepEqual(doc, docBefore, "apply changed its input document");
        assert.deepEqual(step.answer, answerBefore, "apply changed the answer");
        // nothing is shared: changing the result changes neither input
        for (const layer of ["known", "present", "people"]) {
          if (next[layer]) for (const k of Object.keys(next[layer])) delete next[layer][k];
        }
        assert.deepEqual(doc, docBefore);
        assert.deepEqual(step.answer, answerBefore);
        doc = apply(doc, step.answer);
      }
    });
  }
}

test("a vector's start document is not changed by replaying it", () => {
  const suite = vectors("view-feed-people-v1.json");
  const before = structuredClone(suite.sequences[0].start);
  let doc = suite.sequences[0].start;
  for (const step of suite.sequences[0].steps) doc = apply(doc, step.answer);
  assert.deepEqual(suite.sequences[0].start, before);
});

const EMPTY = emptyDocument("w", "knows:person:mara");
const keyed = { ...EMPTY, present: {} };
const withPeople = { ...EMPTY, people: {} };
const answer = (ops, extra = {}) => ({ cursor: "c", at: 1.0, present_on: false, ops, ...extra });

// test 1: every error the Python apply raises, with its message
test("an answer without a clear must keep present_on", () => {
  assert.throws(() => apply(keyed, answer([], { present_on: false })),
    { message: "an answer without a clear must keep the document's present_on" });
  assert.throws(() => apply(EMPTY, answer([], { present_on: true })),
    { message: "an answer without a clear must keep the document's present_on" });
});

test("an answer without a clear must keep the people mode", () => {
  const message = "an answer without a clear must keep the document's people mode";
  assert.throws(() => apply(withPeople, answer([])), { message });
  assert.throws(() => apply(EMPTY, answer([], { people_on: true })), { message });
  // people_on must be exactly true
  assert.throws(() => apply(EMPTY, answer([], { people_on: "yes" })) && apply(withPeople, answer([], { people_on: 1 })), { message });
});

test("reveal on a document with no present layer", () => {
  assert.throws(() => apply(EMPTY, answer([{ op: "reveal", handle: "h:1", id: "obj:a" }])),
    { message: "reveal on a document with no present layer" });
});

test("del and put to a null or missing layer", () => {
  assert.throws(() => apply(EMPTY, answer([{ op: "put", layer: "present", key: "h:1", value: {} }])),
    { message: "put to the present layer while it is null" });
  assert.throws(() => apply(EMPTY, answer([{ op: "del", layer: "present", key: "h:1" }])),
    { message: "del to the present layer while it is null" });
  assert.throws(() => apply(EMPTY, answer([{ op: "put", layer: "people", key: "person:a", value: {} }])),
    { message: "put to the people layer while it is null" });
  assert.throws(() => apply(EMPTY, answer([{ op: "del", layer: "people", key: "person:a" }])),
    { message: "del to the people layer while it is null" });
});

test("an unknown op", () => {
  assert.throws(() => apply(EMPTY, answer([{ op: "frob" }])), { message: "unknown op 'frob'" });
});

test("clear sets the layers by the answer's modes", () => {
  const doc = apply({ ...EMPTY, known: { "obj:a": 1 }, present: { "h:1": 1 }, people: { "person:a": 1 } },
    answer([{ op: "clear" }], { present_on: false }));
  assert.deepEqual(doc, { ...EMPTY, at: 1.0, cursor: "c" });
  assert.ok(!("people" in doc));
  const on = apply(EMPTY, answer([{ op: "clear" }], { present_on: true, people_on: true }));
  assert.deepEqual(on.present, {});
  assert.deepEqual(on.people, {});
});

test("a put of __proto__ lands as data, not as a prototype change", () => {
  const doc = apply(EMPTY, answer([{ op: "put", layer: "known", key: "__proto__", value: { facts: [] } }]));
  assert.ok(Object.prototype.hasOwnProperty.call(doc.known, "__proto__"));
  assert.equal(Object.getPrototypeOf(doc.known), Object.prototype);
  assert.equal({}.facts, undefined);
});

test("sameDocument: key order is free, array order and values count", () => {
  assert.ok(sameDocument({ a: 1, b: [1, { c: 2, d: null }] }, { b: [1, { d: null, c: 2 }], a: 1 }));
  assert.ok(sameDocument(1220.0, 1220));
  assert.ok(!sameDocument([1, 2], [2, 1]));
  assert.ok(!sameDocument({ a: 1 }, { a: 1, b: 2 }));
  assert.ok(!sameDocument({ a: 1, b: 2 }, { a: 1, c: 2 }));
  assert.ok(!sameDocument({ a: null }, { a: undefined }));
  assert.ok(!sameDocument([], {}));
  assert.ok(!sameDocument(null, {}));
});

test("accessors read the document and answer undefined for what it does not hold", () => {
  const suite = vectors("view-feed-people-v1.json");
  const seq = suite.sequences[0];
  let doc = seq.start;
  for (const step of seq.steps) doc = apply(doc, step.answer);
  const someKnown = Object.keys(doc.known)[0];
  assert.equal(known(doc, someKnown), doc.known[someKnown]);
  assert.equal(known(doc, "obj:nobody"), undefined);
  assert.equal(known(doc, "constructor"), undefined);
  assert.equal(present(doc), doc.present);
  assert.equal(present(doc, "h:none"), undefined);
  assert.equal(people(doc), doc.people);
  assert.equal(people(doc, "person:nobody"), undefined);
  assert.equal(people(EMPTY), undefined);
  assert.equal(present(EMPTY), null);
  assert.equal(present(EMPTY, "h:1"), undefined);
  const somePerson = Object.keys(doc.people ?? {})[0];
  if (somePerson) assert.equal(people(doc, somePerson), doc.people[somePerson]);
  const handle = Object.keys(doc.present ?? {})[0];
  if (handle) assert.equal(present(doc, handle), doc.present[handle]);
});
