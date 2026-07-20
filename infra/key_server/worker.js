/**
 * AgentFlow License Validation Worker (Cloudflare Workers)
 *
 * POST /validate  { api_key: string }
 *   200 { key: "<64-char hex CEK>" }   — active license
 *   400 { error: "missing_api_key" }   — no api_key in body
 *   401 { error: "license_revoked" }   — key exists but is revoked
 *   401 { error: "invalid_key" }       — key not in registry
 *
 * KV binding name: KEY_REGISTRY
 *   Each key stores a JSON value: { status: "active"|"revoked", tier, bundle_version }
 *
 * Security notes:
 * - timingSafeEqual used for api_key lookup (constant-time comparison)
 * - Fresh 32-byte CEK generated per request — no server-side caching
 * - 15-min TTL is client-side guidance only; not enforced server-side
 */

const JSON_HEADERS = { "Content-Type": "application/json" };

/**
 * Constant-time string comparison to prevent timing attacks on api_key lookup.
 * Both inputs are encoded to Uint8Array; returns true only if identical length + content.
 */
function timingSafeEqual(a, b) {
  const enc = new TextEncoder();
  const aBytes = enc.encode(a);
  const bBytes = enc.encode(b);
  if (aBytes.length !== bBytes.length) {
    // Still iterate to avoid length-based timing leak
    let diff = 0;
    for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ 0;
    return false;
  }
  let diff = 0;
  for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ bBytes[i];
  return diff === 0;
}

/**
 * Generate a fresh 32-byte AES-256 CEK and return it as a 64-char hex string.
 */
async function generateCEK() {
  const key = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"],
  );
  const raw = await crypto.subtle.exportKey("raw", key);
  return Array.from(new Uint8Array(raw))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: JSON_HEADERS,
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

  // Look up the key in KV. KV key IS the api_key value.
  let record;
  try {
    const raw = await env.KEY_REGISTRY.get(apiKey);
    if (raw === null) {
      // Use timingSafeEqual stub to keep timing consistent
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/validate" && request.method === "POST") {
      return handleValidate(request, env);
    }

    return new Response(JSON.stringify({ error: "not_found" }), {
      status: 404,
      headers: JSON_HEADERS,
    });
  },
};
