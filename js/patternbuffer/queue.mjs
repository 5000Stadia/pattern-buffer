// queue.mjs: calls waiting for a service to be reachable (VIEW-JS-V1 §3).
//
// A persisted FIFO of `{verb: "record", args}`. The queue never applies its
// calls to the document: the document holds only the server's answers, and the
// overlay of pending writes is the game's to draw.
//
// Delivery is at least once. A call whose answer was lost is sent again on the
// next flush, which is why an accrual (`value_type: "delta"`) is refused.

import { askPersist, joinKey, withLock } from "./lock.mjs";
import { checkBackend } from "./backend.mjs";

// service.py _RECORD_KEYS and _RECORD_VALUE_TYPES (delta left out, see above)
const RECORD_KEYS = new Set(["entity", "attribute", "value", "value_type",
  "valid_from", "valid_to", "timeless"]);
const VALUE_TYPES = new Set(["entity", "literal"]);
// model.ID_RE, the engine's whole-id shape
const ID_RE = /^[a-z][a-z0-9_]*:[a-z0-9_:]+$/;
const KNOWS_PREFIX = "knows:";
const ROLES = new Set(["recorder", "author"]);

/** The storage key, and the flush lock name, of a queue. */
export function queueKey(worldId, session) {
  return joinKey("pb:queue", worldId, session);
}

// adds and removals take a short lock of their own, so an `add` never waits
// for the network while a flush holds the queue's key
function writeLockName(worldId, session) {
  return joinKey("pb:queuew", worldId, session);
}

function needString(value, name) {
  if (typeof value !== "string" || value === "") {
    throw new TypeError(`openQueue: ${name} is a non-empty string`);
  }
}

function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function checkItems(items) {
  if (!Array.isArray(items) || items.length === 0) {
    throw new TypeError("record needs a non-empty list of items");
  }
  items.forEach((item, i) => {
    if (!isObject(item)) throw new TypeError(`record item ${i} is not an object`);
    if ("frame" in item || "status" in item) {
      throw new TypeError(`record item ${i} names its own frame/status: the service sets both`);
    }
    const extra = Object.keys(item).filter((k) => !RECORD_KEYS.has(k)).sort();
    if (extra.length > 0) {
      throw new TypeError(`record item ${i} carries keys a play event may not: ${extra.join(", ")}`);
    }
    if (typeof item.entity !== "string" || typeof item.attribute !== "string") {
      throw new TypeError(`record item ${i} needs a string entity and a string attribute`);
    }
    const valueType = item.value_type ?? "literal";
    if (valueType === "delta") {
      throw new TypeError(`record item ${i}: a delta (accrual) could count twice when a call is sent again; not queued in V1`);
    }
    if (!VALUE_TYPES.has(valueType)) {
      throw new TypeError(`record item ${i}: value_type must be one of entity, literal`);
    }
  });
}

/**
 * Open the queue for `(worldId, session)`.
 *
 * @param {object} options
 * @param {object} options.backend `{get, put, del}`, async
 * @param {string} options.worldId namespaces the key and the lock
 * @param {string} options.session the runner session name; every flushed body names it
 * @param {"recorder"|"author"} options.role as the host configured that session; required
 * @param {(call: object) => void} [options.onRefused] called with each refused call
 *   (which is dropped); without it a refusal is logged with console.warn
 * @returns {Promise<Queue>} with `add`, `flush`, `pending`, `persisted`
 */
export async function openQueue({ backend, worldId, session, role, onRefused } = {}) {
  checkBackend(backend);
  needString(worldId, "worldId");
  needString(session, "session");
  if (!ROLES.has(role)) {
    throw new TypeError(`openQueue: role is "recorder" or "author", got ${JSON.stringify(role)}`);
  }
  if (onRefused !== undefined && typeof onRefused !== "function") {
    throw new TypeError("openQueue: onRefused is a function");
  }
  const key = queueKey(worldId, session);
  const writeLock = writeLockName(worldId, session);
  const persisted = await askPersist();

  const read = async () => (await backend.get(key)) ?? [];

  function refused(call) {
    try {
      if (onRefused) onRefused(call);
      else console.warn("patternbuffer queue: the service refused a record; dropped", call);
    } catch (error) {
      console.error("patternbuffer queue: onRefused threw", error);
    }
  }

  // drop the head of the queue, which is the call a flush just got an answer for
  const dropHead = () => withLock(backend, writeLock, async () => {
    const calls = await read();
    calls.shift();
    await backend.put(key, calls);
  });

  const queue = {
    /** Whether the browser agreed to keep this origin's storage; `null` without the API. */
    persisted,

    /**
     * Validate a record call locally and persist it. Throws (rejects) at once
     * on a malformed call; the server checks again. `frame` is passed only
     * when given: an author's, "canon" or "knows:<id>".
     */
    async add(items, options = {}) {
      if (!isObject(options)) throw new TypeError("add: options is {at, frame}");
      const unknown = Object.keys(options).filter((k) => k !== "at" && k !== "frame");
      if (unknown.length > 0) throw new TypeError(`add: unknown option(s) ${unknown.join(", ")}`);
      const { at, frame } = options;
      checkItems(items);
      if (at !== undefined && at !== null
          && (typeof at !== "number" || !Number.isFinite(at))) {
        throw new TypeError("add: at is a number");
      }
      // A timed item with no time of its own would be stamped by the server's
      // now() on each delivery, so a retry after a lost answer would write a
      // different fact. Every queued timed item carries its time (VIEW-JS-V1 §3 r2.1).
      const hasAt = typeof at === "number";
      items.forEach((item, i) => {
        const timed = item.timeless !== true;
        if (timed && (item.valid_from === undefined || item.valid_from === null) && !hasAt) {
          throw new TypeError(`record item ${i} is timed but carries no time: give it valid_from, or add(items, {at}), so a retry repeats the same call`);
        }
      });
      if (frame !== undefined && frame !== null) {
        if (role === "recorder") {
          throw new TypeError("add: a recorder session cannot name a frame");
        }
        if (!(typeof frame === "string"
            && (frame === "canon"
              || (frame.startsWith(KNOWS_PREFIX) && ID_RE.test(frame.slice(KNOWS_PREFIX.length)))))) {
          throw new TypeError(`add: an author's frame is "canon" or "knows:<observer id>", got ${JSON.stringify(frame)}`);
        }
      }
      // the wire's own form: JSON values only
      const args = { items: JSON.parse(JSON.stringify(items)) };
      if (at !== undefined && at !== null) args.at = at;
      if (frame !== undefined && frame !== null) args.frame = frame;
      const call = { verb: "record", args };
      await withLock(backend, writeLock, async () => {
        const calls = await read();
        calls.push(call);
        await backend.put(key, calls);
      });
    },

    /**
     * Send the waiting calls in order, one at a time, under the queue's lock.
     * `recorded` drops a call; `refused` or a 400 drops it and reports it
     * through `onRefused`; a thrown transport, a 5xx, a 504 or any answer this
     * module does not understand stops the flush and keeps that call and the
     * rest. Resolves with how many calls got a final answer.
     */
    flush(transport) {
      return withLock(backend, key, async () => {
        let sent = 0;
        for (;;) {
          const calls = await read();
          if (calls.length === 0) return sent;
          const call = calls[0];
          let response;
          try {
            response = await transport({ session, verb: call.verb, args: call.args });
          } catch {
            return sent;
          }
          const status = response?.status;
          const outcome = status === 200 ? response.json?.result?.status : undefined;
          if (outcome === "recorded") {
            await dropHead();
          } else if (outcome === "refused" || status === 400) {
            await dropHead();
            refused(call);
          } else {
            return sent;
          }
          sent += 1;
        }
      });
    },

    /** The waiting calls, oldest first, as a copy. */
    async pending() {
      return read();
    },
  };
  return queue;
}
