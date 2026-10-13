# patternbuffer (browser view module)

Small ES modules for a browser client of a pattern-buffer world: the port of
`patternbuffer.mirror.apply`, a view that persists across reloads, and a queue of
`record` calls waiting for a service. No dependencies, no build step. Spec:
`specs/VIEW-JS-V1.md`.

The device holds the answers the service gives and never works them out: there is
no fold, no identity and no cursor arithmetic here. Absent from the document means
unknown to the player.

```js
import { openView, openQueue, idbBackend, httpTransport, known } from "./patternbuffer/index.mjs";

const backend = idbBackend("my-game");
const transport = httpTransport("http://127.0.0.1:8765");

const view = await openView({ backend, worldId: "w:manor", viewFrame: "knows:person:mara",
                              session: "viewer", seed: await (await fetch("view.json")).json() });
await view.sync(transport);          // on arrival, after a flush, on a timer; never per frame
known(view.doc, "obj:desk");         // { facts, conflicted } or undefined

const queue = await openQueue({ backend, worldId: "w:manor", session: "photonic", role: "author",
                                onRefused: (call) => console.log("refused", call) });
await queue.add([{ entity: "person:cook", attribute: "posture", value: "sitting" }], { frame: "canon" });
await queue.flush(transport);        // in order; stops at the first failure and keeps the rest
```

Files: `view.mjs` (`apply`, `sameDocument`, `known`, `present`, `people`),
`store.mjs` (`openView`), `queue.mjs` (`openQueue`), `idb.mjs` (`idbBackend`),
`backend.mjs` (`memoryBackend`), `transport.mjs` (`httpTransport`), `lock.mjs`
(internal), `index.mjs` (re-exports).

## Notes

- **Python is the reference.** `patternbuffer.mirror.apply` and the vectors in
  `tests/vectors/view-feed-v1.json` and `view-feed-people-v1.json` decide. The
  tests in `js/test` replay them, and `tests/test_js_module.py` runs those tests
  in the Python suite, so a contract change fails here until the port follows.
- **Vendoring.** Copy `js/patternbuffer/` at a tagged commit. The directory is
  self-contained; `js/test` and the vectors need not travel.
- **Running the tests.** `node --test js/test/*.test.mjs` (node 18 or newer;
  `structuredClone` needs 17). Name the files: from node 21 on, `node --test
  js/test` reads the directory as a script. IndexedDB tests skip where there is no
  global `indexedDB`.
- **Delivery is at least once.** A queued call whose answer was lost is sent
  again, so `add` refuses `value_type: "delta"`.
- **Today's runner** serves loopback hosts only and grants no cross-origin
  requests, so a page served from elsewhere cannot reach it; the queue waits.
