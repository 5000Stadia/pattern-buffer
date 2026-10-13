// helpers shared by the tests: the committed vectors, a fake navigator, a fake transport.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));

export function vectors(name) {
  return JSON.parse(readFileSync(path.join(here, "..", "..", "tests", "vectors", name), "utf8"));
}

/** Set globalThis.navigator for one test body; always restores it. */
export async function withNavigator(fake, body) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", { value: fake, configurable: true, writable: true });
  try {
    return await body();
  } finally {
    if (original) Object.defineProperty(globalThis, "navigator", original);
    else delete globalThis.navigator;
  }
}

/** A navigator.locks that takes turns per name, and records every name asked for. */
export function fakeLocks() {
  const tails = new Map();
  const names = [];
  let held = 0;
  let maxHeld = 0;
  return {
    names,
    get maxHeld() { return maxHeld; },
    request(name, callback) {
      names.push(name);
      const before = tails.get(name) ?? Promise.resolve();
      const run = before.then(async () => {
        held += 1;
        maxHeld = Math.max(maxHeld, held);
        try { return await callback({ name }); } finally { held -= 1; }
      });
      tails.set(name, run.then(() => undefined, () => undefined));
      return run;
    },
  };
}

export const ok = (result) => ({ status: 200, json: { result } });
export const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
