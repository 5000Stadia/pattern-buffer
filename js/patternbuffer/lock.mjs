// lock.mjs: one writer at a time per storage key (VIEW-JS-V1 §2, §3).
//
// Where `navigator.locks` exists (Safari 15.4+, every current browser), the
// lock is the browser's, so two tabs on one origin take turns. Where it does
// not (node, old browsers), a promise chain per (backend, name) takes its
// place, which serializes every caller in this page.

const chains = new WeakMap();

/** Run `fn` while holding the lock `name` on `backend`; resolves with its result. */
export function withLock(backend, name, fn) {
  const locks = globalThis.navigator?.locks;
  if (locks && typeof locks.request === "function") {
    return locks.request(name, () => fn());
  }
  let byName = chains.get(backend);
  if (byName === undefined) {
    byName = new Map();
    chains.set(backend, byName);
  }
  const before = byName.get(name) ?? Promise.resolve();
  const run = before.then(() => fn());
  const tail = run.then(() => undefined, () => undefined);
  byName.set(name, tail);
  tail.then(() => {
    if (byName.get(name) === tail) byName.delete(name);
  });
  return run;
}

/** `encodeURIComponent` each part, so a ":" inside one can't make two keys collide. */
export function joinKey(prefix, ...parts) {
  return [prefix, ...parts.map((part) => encodeURIComponent(part))].join(":");
}

/** Ask the browser to keep this origin's storage: `true`, `false`, or `null` without the API. */
export async function askPersist() {
  const storage = globalThis.navigator?.storage;
  if (!storage || typeof storage.persist !== "function") return null;
  try {
    return (await storage.persist()) === true;
  } catch {
    return false;
  }
}
