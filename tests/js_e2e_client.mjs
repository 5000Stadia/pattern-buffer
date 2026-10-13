// The end-to-end client for tests/test_js_module.py (VIEW-JS-V1 test 5).
// usage: node tests/js_e2e_client.mjs BASE_URL WORLD_ID VIEW_FRAME VIEWER_SESSION AUTHOR_SESSION
// Opens a view over httpTransport, syncs, queues an author record (a person moved
// in canon), flushes, syncs again, syncs once more (nothing new), and prints one
// JSON object for the Python test to compare with mirror.export.
import { httpTransport, memoryBackend, openQueue, openView } from "../js/patternbuffer/index.mjs";

const [baseUrl, worldId, viewFrame, viewerSession, authorSession] = process.argv.slice(2);
const transport = httpTransport(baseUrl, { timeoutMs: 20000 });
const backend = memoryBackend();

const view = await openView({ backend, worldId, viewFrame, session: viewerSession });
const first = structuredClone(await view.sync(transport));

const queue = await openQueue({ backend, worldId, session: authorSession, role: "author" });
await queue.add([{
  entity: "person:cook", attribute: "in", value: "place:bedroom", value_type: "entity",
  timeless: false, valid_from: 5.0,
}], { at: 5.0, frame: "canon" });
const waiting = (await queue.pending()).length;
const sent = await queue.flush(transport);
const left = (await queue.pending()).length;

const second = structuredClone(await view.sync(transport));
const third = structuredClone(await view.sync(transport));
console.log(JSON.stringify({ first, waiting, sent, left, second, third }));
