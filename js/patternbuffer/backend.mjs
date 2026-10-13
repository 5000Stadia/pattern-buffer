// backend.mjs: the storage contract and an in-memory backend for tests.
//
// A backend is `{get(key), put(key, value), del(key)}`, every method async.
// `get` answers `undefined` for an absent key. Values are copied on the way in
// and out, as IndexedDB's structured clone does, so a caller never shares an
// object with the store.

export function memoryBackend() {
  const store = new Map();
  return {
    async get(key) {
      return store.has(key) ? structuredClone(store.get(key)) : undefined;
    },
    async put(key, value) {
      store.set(key, structuredClone(value));
    },
    async del(key) {
      store.delete(key);
    },
  };
}

/** Whether `backend` has the three methods the module calls. */
export function checkBackend(backend) {
  for (const method of ["get", "put", "del"]) {
    if (!backend || typeof backend[method] !== "function") {
      throw new TypeError(`backend needs async get, put and del; ${method} is missing`);
    }
  }
}
