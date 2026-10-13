// store.mjs: a view that survives a reload (VIEW-JS-V1 §2).
//
// One persisted document per (world, view frame). `sync` asks the service for
// what changed since the document's cursor and applies the answer; the device
// holds the answers and never works them out.

import { apply, emptyDocument } from "./view.mjs";
import { askPersist, joinKey, withLock } from "./lock.mjs";
import { checkBackend } from "./backend.mjs";

/** The storage key, and the lock name, of a view's document. */
export function viewKey(worldId, viewFrame) {
  return joinKey("pb:view", worldId, viewFrame);
}

function needString(value, name) {
  if (typeof value !== "string" || value === "") {
    throw new TypeError(`openView: ${name} is a non-empty string`);
  }
}

function plainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** What a failed call says, for an Error message (the service's {"error": {message}}). */
function describe(response) {
  const error = response?.json?.error;
  const text = error ? `${error.type ?? "error"}: ${error.message ?? ""}` : "no result";
  return `HTTP ${response?.status}: ${text}`;
}

/**
 * Open the view for `(worldId, viewFrame)`.
 *
 * @param {object} options
 * @param {object} options.backend `{get, put, del}`, async
 * @param {string} options.worldId
 * @param {string} options.viewFrame the player's frame, e.g. "knows:person:mara"
 * @param {string} options.session the runner session name `feed` calls use (any role may read)
 * @param {object} [options.seed] the static view.json the page ships; the empty document by default
 * @returns {Promise<View>} with `doc`, `reseeded`, `persisted`, `sync(transport)`, `replace(document)`
 */
export async function openView({ backend, worldId, viewFrame, session, seed } = {}) {
  checkBackend(backend);
  needString(worldId, "worldId");
  needString(viewFrame, "viewFrame");
  needString(session, "session");
  if (seed !== undefined && !plainObject(seed)) {
    throw new TypeError("openView: seed is a view document");
  }
  const key = viewKey(worldId, viewFrame);
  const persisted = await askPersist();

  // the seed is written at once, so a reopen is told it is not a fresh start
  const { doc, reseeded } = await withLock(backend, key, async () => {
    const stored = await backend.get(key);
    if (stored !== undefined && stored !== null) return { doc: stored, reseeded: false };
    const start = seed === undefined ? emptyDocument(worldId, viewFrame)
      : structuredClone(seed);
    await backend.put(key, start);
    return { doc: start, reseeded: true };
  });

  const view = {
    /** The current document: the server's answers applied, nothing else. */
    doc,
    /** `true` when no persisted document was found and the seed was loaded. */
    reseeded,
    /** Whether the browser agreed to keep this origin's storage; `null` without the API. */
    persisted,

    /**
     * Ask for the changes since the document's cursor, apply them, persist,
     * then replace `view.doc`. Resolves with the new document. If the call
     * fails or `apply` throws, the persisted and current documents are
     * unchanged and the promise rejects.
     */
    sync(transport) {
      return withLock(backend, key, async () => {
        // another tab may have synced since we last looked: carry on from its cursor
        const stored = await backend.get(key);
        const base = stored ?? view.doc;
        const args = {};
        if (base.cursor !== null && base.cursor !== undefined) args.since = base.cursor;
        const response = await transport({ session, verb: "feed", args });
        if (response?.status !== 200 || !response.json
            || !plainObject(response.json.result)) {
          throw new Error(`sync: ${describe(response)}`);
        }
        const next = apply(base, response.json.result);
        await backend.put(key, next);
        view.doc = next;
        return next;
      });
    },

    /** Persist a fresh export (a page that downloaded a new view.json). */
    replace(document) {
      if (!plainObject(document)) throw new TypeError("replace: a view document");
      return withLock(backend, key, async () => {
        const next = structuredClone(document);
        await backend.put(key, next);
        view.doc = next;
        return next;
      });
    },
  };
  return view;
}
