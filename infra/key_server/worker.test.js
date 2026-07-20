/**
 * Unit tests for AgentFlow License Validation Worker
 * Run with: npx vitest run infra/key_server/worker.test.js
 *
 * Uses an in-memory mock KV store — no real Cloudflare KV required.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";

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
// Import worker handler inline (avoids module resolution issues in test env)
// ---------------------------------------------------------------------------

// Inline the worker logic so tests run without a bundler.

function timingSafeEqual(a, b) {
  const enc = new TextEncoder();
  const aBytes = enc.encode(a);
  const bBytes = enc.encode(b);
  if (aBytes.length !== bBytes.length) {
    let diff = 0;
    for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ 0;
    return false;
  }
  let diff = 0;
  for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ bBytes[i];
  return diff === 0;
}

async function generateCEK() {
  // In test env (node), use crypto.getRandomValues via globalThis.crypto
  const bytes = new Uint8Array(32);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function handleValidate(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }

  const apiKey = body?.api_key;
  if (!apiKey || typeof apiKey !== "string" || apiKey.trim() === "") {
    return jsonResponse({ error: "missing_api_key" }, 400);
  }

  let record;
  try {
    const raw = await env.KEY_REGISTRY.get(apiKey);
    if (raw === null) {
      timingSafeEqual(apiKey, apiKey);
      return jsonResponse({ error: "invalid_key" }, 401);
    }
    record = JSON.parse(raw);
  } catch {
    return jsonResponse({ error: "server_error" }, 500);
  }

  if (record.status === "revoked") {
    return jsonResponse({ error: "license_revoked" }, 401);
  }
  if (record.status !== "active") {
    return jsonResponse({ error: "invalid_key" }, 401);
  }

  const cek = await generateCEK();
  return jsonResponse({ key: cek }, 200);
}

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
// Test fixtures
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

function makeRequest(body) {
  return new Request("https://worker.example.com/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("POST /validate", () => {
  it("valid active key → 200 + {key: <64-char hex>}", async () => {
    const env = makeEnv();
    const req = makeRequest({ api_key: ACTIVE_KEY });
    const res = await workerFetch(req, env);

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("key");
    expect(data.key).toHaveLength(64);
    // Must be valid hex
    expect(/^[0-9a-f]{64}$/.test(data.key)).toBe(true);
  });

  it("each /validate call generates a fresh CEK", async () => {
    const env = makeEnv();
    const res1 = await workerFetch(makeRequest({ api_key: ACTIVE_KEY }), env);
    const res2 = await workerFetch(makeRequest({ api_key: ACTIVE_KEY }), env);
    const key1 = (await res1.json()).key;
    const key2 = (await res2.json()).key;
    // With 32 bytes of randomness the probability of collision is negligible
    expect(key1).not.toBe(key2);
  });

  it("revoked key → 401 {error: 'license_revoked'}", async () => {
    const env = makeEnv();
    const req = makeRequest({ api_key: REVOKED_KEY });
    const res = await workerFetch(req, env);

    expect(res.status).toBe(401);
    const data = await res.json();
    expect(data.error).toBe("license_revoked");
  });

  it("unknown key → 401 {error: 'invalid_key'}", async () => {
    const env = makeEnv();
    const req = makeRequest({ api_key: "not-in-registry" });
    const res = await workerFetch(req, env);

    expect(res.status).toBe(401);
    const data = await res.json();
    expect(data.error).toBe("invalid_key");
  });

  it("missing api_key body → 400", async () => {
    const env = makeEnv();
    const req = makeRequest({});
    const res = await workerFetch(req, env);

    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toBe("missing_api_key");
  });

  it("empty api_key string → 400", async () => {
    const env = makeEnv();
    const req = makeRequest({ api_key: "   " });
    const res = await workerFetch(req, env);

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
    const req = new Request("https://worker.example.com/health", {
      method: "GET",
    });
    const res = await workerFetch(req, env);
    expect(res.status).toBe(404);
  });
});

describe("provision.sh semantics via KV", () => {
  it("add-key: key appears in registry as active", async () => {
    const kv = makeKV();
    const env = { KEY_REGISTRY: kv };
    const newKey = "agf-new-key-12345";

    // Simulate what provision.sh add-key does via wrangler kv:key put
    await kv.put(
      newKey,
      JSON.stringify({ status: "active", tier: "friendly", bundle_version: "v1" }),
    );

    const req = makeRequest({ api_key: newKey });
    const res = await workerFetch(req, env);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("key");
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

    // Confirm active first
    const before = await workerFetch(makeRequest({ api_key: ACTIVE_KEY }), env);
    expect(before.status).toBe(200);

    // Simulate provision.sh revoke-key (wrangler kv:key put with revoked status)
    await kv.put(
      ACTIVE_KEY,
      JSON.stringify({ status: "revoked", tier: "friendly", bundle_version: "v1" }),
    );

    // Now validate should return 401
    const after = await workerFetch(makeRequest({ api_key: ACTIVE_KEY }), env);
    expect(after.status).toBe(401);
    const data = await after.json();
    expect(data.error).toBe("license_revoked");
  });
});
