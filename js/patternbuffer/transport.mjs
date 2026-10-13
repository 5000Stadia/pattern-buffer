// transport.mjs: `POST {baseUrl}/call` for the runner (VIEW-JS-V1 §4).
//
// A transport is `async (body) => ({status, json})` where `body` is
// `{session, verb, args}`. `json` is the parsed response body, or `null` when
// the body was not JSON. A network failure throws; the callers treat a throw as
// "try again later".

/**
 * @param {string} baseUrl e.g. "http://127.0.0.1:8765"
 * @param {{fetch?: Function, timeoutMs?: number}} [options] `timeoutMs` (default
 *   15000, 0 for none) keeps a hung request from holding a queue's lock forever.
 */
export function httpTransport(baseUrl, { fetch: fetchFn, timeoutMs = 15000 } = {}) {
  const url = String(baseUrl).replace(/\/+$/, "") + "/call";
  return async (body) => {
    const doFetch = fetchFn ?? globalThis.fetch;
    const init = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
    if (timeoutMs > 0 && typeof AbortSignal?.timeout === "function") {
      init.signal = AbortSignal.timeout(timeoutMs);
    }
    const response = await doFetch(url, init);
    let json = null;
    try {
      json = await response.json();
    } catch {
      json = null;
    }
    return { status: response.status, json };
  };
}
