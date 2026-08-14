/**
 * Forward Pass — subscribe/unsubscribe relay (Cloudflare Worker).
 *
 * The GitHub Pages site is static, so the subscribe form can't call the
 * Resend API directly without exposing the API key. This Worker is the
 * thin server-side relay:
 *
 *   POST /subscribe      {email} → adds the contact to the Resend Audience
 *                        (re-subscribes it if it was previously unsubscribed)
 *   GET  /unsubscribe    ?e=<base64url email>&t=<hmac> → marks unsubscribed,
 *                        shows a one-line confirmation page
 *   POST /unsubscribe    same params — RFC 8058 one-click (Gmail/Yahoo hit
 *                        this silently from the inbox "Unsubscribe" button)
 *
 * Deploy: Cloudflare dashboard → Workers → Create → paste this file.
 * Settings → Variables and Secrets:
 *   RESEND_API_KEY (secret)  Resend API key
 *   UNSUB_SECRET   (secret)  any long random string; MUST equal the
 *                            UNSUB_SECRET env var of the newsletter run
 *   ALLOWED_ORIGIN (var)     https://gblayer.github.io
 *
 * Contacts use Resend's account-level API (POST/PATCH /contacts) — the
 * older audience-scoped endpoints are gone from new Resend accounts.
 */

const RESEND = "https://api.resend.com";

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function json(body, status, env) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}

async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function b64urlDecode(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return atob(s);
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

async function resend(env, method, path, body) {
  return fetch(`${RESEND}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function subscribe(req, env) {
  let email = "";
  const ct = req.headers.get("Content-Type") || "";
  if (ct.includes("application/json")) {
    email = ((await req.json().catch(() => ({}))).email || "").trim().toLowerCase();
  } else {
    email = ((await req.formData().catch(() => new FormData())).get("email") || "")
      .toString().trim().toLowerCase();
  }
  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "invalid email" }, 400, env);

  const create = await resend(env, "POST", "/contacts",
    { email, unsubscribed: false });
  if (create.ok) return json({ ok: true }, 200, env);

  // Already a contact (e.g. previously unsubscribed) → flip it back on.
  const update = await resend(env, "PATCH", `/contacts/${email}`,
    { unsubscribed: false });
  if (update.ok) return json({ ok: true }, 200, env);

  return json({ ok: false, error: "could not subscribe, try again later" }, 502, env);
}

async function unsubscribe(req, env, url) {
  const e = url.searchParams.get("e") || "";
  const t = url.searchParams.get("t") || "";
  let email = "";
  try { email = b64urlDecode(e).trim().toLowerCase(); } catch { /* fall through */ }
  const expected = email ? await hmacHex(env.UNSUB_SECRET, email) : "";
  if (!email || !expected || t !== expected) {
    return new Response("Invalid unsubscribe link.", { status: 400, headers: cors(env) });
  }

  await resend(env, "PATCH", `/contacts/${email}`, { unsubscribed: true });

  // One-click (RFC 8058) POSTs from the inbox expect a bare 200.
  if (req.method === "POST") return new Response("OK", { status: 200, headers: cors(env) });

  return new Response(
    `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Unsubscribed</title></head>
     <body style="margin:0;background:#17160f;color:#f6f5f0;font-family:Arial,sans-serif;
                  display:flex;align-items:center;justify-content:center;height:100vh;">
       <div style="text-align:center;">
         <div style="font-size:26px;font-weight:700;">
           <span style="color:#3b38f5;">&raquo;</span>FP<span style="color:#ff5a1f;">.</span></div>
         <p style="color:#c3c0b4;">You're unsubscribed. No more emails.</p>
       </div>
     </body></html>`,
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8", ...cors(env) } },
  );
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });
    if (url.pathname === "/subscribe" && req.method === "POST") return subscribe(req, env);
    if (url.pathname === "/unsubscribe") return unsubscribe(req, env, url);
    return new Response("Not found", { status: 404, headers: cors(env) });
  },
};
