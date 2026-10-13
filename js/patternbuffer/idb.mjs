// idb.mjs: the browser's backend, over IndexedDB (VIEW-JS-V1 §4). One object
// store; values are structured-cloned by IndexedDB itself. No dependency.

const STORE = "kv";

/**
 * @param {string} dbName
 * @param {{indexedDB?: IDBFactory}} [options] defaults to the global one
 */
export function idbBackend(dbName, { indexedDB: factory } = {}) {
  let opening = null;

  function open() {
    if (opening === null) {
      opening = new Promise((resolve, reject) => {
        const idb = factory ?? globalThis.indexedDB;
        if (!idb) {
          reject(new Error("indexedDB is not available here"));
          return;
        }
        const request = idb.open(dbName, 1);
        request.onupgradeneeded = () => {
          request.result.createObjectStore(STORE);
        };
        request.onsuccess = () => {
          const db = request.result;
          // another tab upgrading the database, or the browser closing it
          db.onversionchange = () => {
            db.close();
            opening = null;
          };
          db.onclose = () => {
            opening = null;
          };
          resolve(db);
        };
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error("indexedDB open is blocked"));
      });
      opening.catch(() => {
        opening = null;
      });
    }
    return opening;
  }

  // one transaction, resolved when it commits (not when the request returns)
  async function run(mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      let result;
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error ?? new Error("indexedDB transaction aborted"));
      const request = action(tx.objectStore(STORE));
      request.onsuccess = () => {
        result = request.result;
      };
    });
  }

  return {
    get: (key) => run("readonly", (store) => store.get(key)),
    put: (key, value) => run("readwrite", (store) => store.put(value, key)).then(() => undefined),
    del: (key) => run("readwrite", (store) => store.delete(key)).then(() => undefined),
  };
}
