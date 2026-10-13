// view.mjs: the browser port of patternbuffer.mirror.apply (VIEW-EXPORT-V1 §3,
// VIEW-PEOPLE-V1 §3). Python's `mirror.apply` is the reference; the committed
// vectors (tests/vectors/view-feed*.json) decide when the two differ.
//
// This module only applies an answer the service gave. It never folds, never
// computes a cursor and never reads an identity: absent means unknown to the
// player, never "does not exist" (VIEW-EXPORT-V1 §7).

export const SCHEMA = "patternbuffer.view/1";

/** The Python `repr` of the few values an error message names (an unknown op). */
function pyRepr(value) {
  if (typeof value === "string") {
    const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
    return quote + value.replaceAll("\\", "\\\\").replaceAll("\n", "\\n")
      .replaceAll(quote, "\\" + quote) + quote;
  }
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  return String(value);
}

/** The empty document for a world and a view frame (`mirror._empty_document`). */
export function emptyDocument(worldId, viewFrame) {
  return {
    schema: SCHEMA, world_id: worldId, view_frame: viewFrame,
    at: null, cursor: null, known: {}, present: null,
  };
}

function own(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

// a key such as "__proto__" must land as data, never as a prototype change
function setOwn(object, key, value) {
  Object.defineProperty(object, key, {
    value, writable: true, enumerable: true, configurable: true,
  });
}

/**
 * A document with a feed answer applied. Pure: the input and the answer are
 * never changed, and the result shares nothing with either. Runs the ops in
 * order; `cursor` and `at` come from the answer. Throws `Error` with the Python
 * message text for the same four faults.
 *
 * It clones the whole document: call it when the game wants fresh state, never
 * from a render loop.
 */
export function apply(document, answer) {
  const out = structuredClone(document);
  const presentOn = answer.present_on;
  const peopleOn = answer.people_on === true;
  const noClear = !answer.ops.some((op) => op.op === "clear");
  if (((out.present ?? null) !== null) !== presentOn && noClear) {
    throw new Error("an answer without a clear must keep the document's present_on");
  }
  if (own(out, "people") !== peopleOn && noClear) {
    throw new Error("an answer without a clear must keep the document's people mode");
  }
  for (const op of answer.ops) {
    const kind = op.op;
    if (kind === "clear") {
      out.known = {};
      out.present = presentOn ? {} : null;
      if (peopleOn) out.people = {};
      else delete out.people;
    } else if (kind === "reveal") {
      if ((out.present ?? null) === null) {
        throw new Error("reveal on a document with no present layer");
      }
      delete out.present[op.handle];
    } else if (kind === "del" || kind === "put") {
      const layer = own(out, op.layer) ? out[op.layer] : null;
      if (layer === null || layer === undefined) {
        throw new Error(`${kind} to the ${op.layer} layer while it is null`);
      }
      if (kind === "del") delete layer[op.key];
      else setOwn(layer, op.key, structuredClone(op.value));
    } else {
      throw new Error(`unknown op ${pyRepr(kind)}`);
    }
  }
  out.cursor = answer.cursor;
  out.at = answer.at;
  return out;
}

/**
 * Deep equality of two JSON values. Object key order is free; array order
 * counts. JS cannot tell 1220.0 from 1220, and no client depends on the
 * difference.
 */
export function sameDocument(a, b) {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) {
    return false;
  }
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    return a.length === b.length && a.every((item, i) => sameDocument(item, b[i]));
  }
  const keys = Object.keys(a);
  if (keys.length !== Object.keys(b).length) return false;
  return keys.every((k) => own(b, k) && sameDocument(a[k], b[k]));
}

/**
 * The player's record of one subject: `{facts, conflicted}`, or `undefined`
 * when the document has no such subject (unknown to the player).
 */
export function known(doc, id) {
  return doc?.known && own(doc.known, id) ? doc.known[id] : undefined;
}

/**
 * The present layer: with a handle, that one drawable record or `undefined`;
 * without, the whole layer (`null` when the document has none).
 */
export function present(doc, handle) {
  const layer = doc?.present ?? null;
  if (handle === undefined) return layer;
  return layer !== null && own(layer, handle) ? layer[handle] : undefined;
}

/**
 * The people layer: with an id, that person's record or `undefined`; without,
 * the whole layer (`undefined` while the layer is off).
 */
export function people(doc, id) {
  const layer = doc && own(doc, "people") ? doc.people : undefined;
  if (id === undefined) return layer;
  return layer !== undefined && own(layer, id) ? layer[id] : undefined;
}
