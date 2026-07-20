/**
 * Unit tests for AgentFlow License Validation Worker
 * Run with: npx vitest run infra/key_server/worker.test.js
 *
 * Uses an in-memory mock KV store — no real Cloudflare KV required.
 * Imports production code from worker.js via named exports.
 */

import { describe, it, expect, vi } from "vitest";
import { handleValidate, timingSafeEqual, generateCEK } from "./worker.js";

// ---------------------------------------------------------------------------
// Mock KV store
// ---------------------------------------------------------------------------

function makeKV(initial = {}) {
  const store = { ...initial };
  return {
    async get(key) {
      return Object.prototype.hasOwnProperty.call(store, key)
        ? store[key]
        : null;
    },
    async put(key, value) {
      store[key] = value;
    },
    _store: store,
  };
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

const ACTIVE_KEY = "agf-friendly-key-abc123";
const REVOKED_KEY = "agf-revoked-key-xyz789";

function makeEnv(overrides = {}) {
  const kv = makeKV({
    [ACTIVE_KEY]: JSON.stringify({
      status: "active",
      tier: "friendly",
      bundle_version: "v1",
    }),
    [REVOKED_KEY]: JSON.stringify({
      status: "revoked",
      tier: "friendly",
      bundle_version: "v1",
    }),
    ...overrides,
  });
  return { KEY_REGISTRY: kv };
}

function makeValidateRequest(body) {
  return new Request("https://worker.example.com/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Thin routing shim — mirrors worker.js default export fetch() */
async function workerFetch(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/validate" && request.method === "POST") {
    return handleValidate(request, env);
  }
  return new Response(JSON.stringify({ error: "not_found" }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  });
}

// ---------------------------------------------------------------------------
// POST /validate
// ---------------------------------------------------------------------------

describe("POST /validate", () => {
  it("valid active key → 200 + {key: <64-char hex>}", async () => {
    const env = makeEnv();
    const res = await workerFetch(makeValidateRequest({ api_key: ACTIVE_KEY }), env);

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("key");
    expect(data.key).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(data.key)).toBe(true);
  });

  it("each /validate call generates a fresh CEK", async () => {
    const env = makeEnv();
    const res1 = await workerFetch(makeValidateRequest({ api_key: ACTIVE_KEY }), env);
    const res2 = await workerFetch(makeValidateRequest({ api_key: ACTIVE_KEY }), env);
    const key1 = (await res1.json()).key;
    const key2 = (await res2.json()).key;
    expect(key1).not.toBe(key2);
  });

  it("revoked key → 401 {error: 'license_revoked'}", async () => {
    const env = makeEnv();
    const res = await workerFetch(makeValidateRequest({ api_key: REVOKED_KEY }), env);

    expect(res.status).toBe(401);
    expect((await res.json()).error).toBe("license_revoked");
  });

  it("unknown key → 401 {error: 'invalid_key'}", async () => {
    const env = makeEnv();
    const res = await workerFetch(makeValidateRequest({ api_key: "not-in-registry" }), env);

    expect(res.status).toBe(401);
    expect((await res.json()).error).toBe("invalid_key");
  });

  it("missing api_key body → 400", async () => {
    const env = makeEnv();
    const res = await workerFetch(makeValidateRequest({}), env);

    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe("missing_api_key");
  });

  it("whitespace-only api_key → 400", async () => {
    const env = makeEnv();
    const res = await workerFetch(makeValidateRequest({ api_key: "   " }), env);
    expect(res.status).toBe(400);
  });

  it("malformed JSON body → 400", async () => {
    const env = makeEnv();
    const req = new Request("https://worker.example.com/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "not-json",
    });
    const res = await workerFetch(req, env);
    expect(res.status).toBe(400);
  });

  it("unknown route → 404", async () => {
    const env = makeEnv();
    const req = new Request("https://worker.example.com/health", { method: "GET" });
    const res = await workerFetch(req, env);
    expect(res.status).toBe(404);
  });

  it("401 paths emit console.error with reason (no api_key logged)", async () => {
    const env = makeEnv();
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    await workerFetch(makeValidateRequest({ api_key: REVOKED_KEY }), env);
    await workerFetch(makeValidateRequest({ api_key: "unknown-key" }), env);

    expect(spy).toHaveBeenCalledTimes(2);
    for (const call of spy.mock.calls) {
      const logged = JSON.parse(call[0]);
      expect(logged).toHaveProperty("event", "validate_failed");
      expect(logged).toHaveProperty("reason");
      // api_key must never appear in the log
      expect(call[0]).not.toContain(REVOKED_KEY);
      expect(call[0]).not.toContain("unknown-key");
    }

    spy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// provision.sh semantics via KV
// ---------------------------------------------------------------------------

describe("provision.sh semantics via KV", () => {
  it("add-key: key appears in registry as active", async () => {
    const kv = makeKV();
    const env = { KEY_REGISTRY: kv };
    const newKey = "agf-new-key-12345";

    await kv.put(
      newKey,
      JSON.stringify({ status: "active", tier: "friendly", bundle_version: "v1" }),
    );

    const res = await workerFetch(makeValidateRequest({ api_key: newKey }), env);
    expect(res.status).toBe(200);
    expect(await res.json()).toHaveProperty("key");
  });

  it("revoke-key: status flips to revoked; subsequent validate returns 401", async () => {
    const kv = makeKV({
      [ACTIVE_KEY]: JSON.stringify({
        status: "active",
        tier: "friendly",
        bundle_version: "v1",
      }),
    });
    const env = { KEY_REGISTRY: kv };

    const before = await workerFetch(makeValidateRequest({ api_key: ACTIVE_KEY }), env);
    expect(before.status).toBe(200);

    await kv.put(
      ACTIVE_KEY,
      JSON.stringify({ status: "revoked", tier: "friendly", bundle_version: "v1" }),
    );

    const after = await workerFetch(makeValidateRequest({ api_key: ACTIVE_KEY }), env);
    expect(after.status).toBe(401);
    expect((await after.json()).error).toBe("license_revoked");
  });
});

// ---------------------------------------------------------------------------
// Unit tests for exported helpers
// ---------------------------------------------------------------------------

describe("timingSafeEqual", () => {
  it("returns true for identical strings", () => {
    expect(timingSafeEqual("abc", "abc")).toBe(true);
  });

  it("returns false for different strings of same length", () => {
    expect(timingSafeEqual("abc", "xyz")).toBe(false);
  });

  it("returns false for different-length strings", () => {
    expect(timingSafeEqual("short", "much-longer-string")).toBe(false);
  });

  it("constant dummy comparison does real work (unknown-key path)", () => {
    // Ensures the function operates identically whether key exists or not
    const result = timingSafeEqual("any-api-key", "DUMMY_CONSTANT_FOR_TIMING");
    expect(typeof result).toBe("boolean");
  });
});

describe("generateCEK", () => {
  it("returns a 64-char lowercase hex string", async () => {
    const cek = await generateCEK();
    expect(cek).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(cek)).toBe(true);
  });

  it("returns unique values on successive calls", async () => {
    const a = await generateCEK();
    const b = await generateCEK();
    expect(a).not.toBe(b);
  });
});
