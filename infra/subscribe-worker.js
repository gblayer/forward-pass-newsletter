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
 * Optional — enables the instant welcome email (sent via the same Gmail
 * account as the newsletter; skipped silently when absent):
 *   GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN (secrets)
 *   SMTP_USER (var)  the Gmail from-address
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

function b64Std(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64urlEncode(str) {
  return b64Std(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Welcome email, sent via the same Gmail account as the newsletter.
 *  Best-effort: any failure is swallowed — the signup itself already succeeded.
 *  Requires the optional Worker secrets GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET /
 *  GMAIL_REFRESH_TOKEN and the var SMTP_USER; silently skipped when absent. */
async function sendWelcome(env, email, origin) {
  if (!env.GMAIL_REFRESH_TOKEN || !env.SMTP_USER) return;
  try {
    const tok = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: env.GMAIL_CLIENT_ID,
        client_secret: env.GMAIL_CLIENT_SECRET,
        refresh_token: env.GMAIL_REFRESH_TOKEN,
        grant_type: "refresh_token",
      }),
    });
    if (!tok.ok) return;
    const access = (await tok.json()).access_token;

    const site = "https://gblayer.github.io/forward-pass-newsletter";
    const unsubUrl =
      `${origin}/unsubscribe?e=${b64urlEncode(email)}&t=${await hmacHex(env.UNSUB_SECRET, email)}`;
    const html =
      `<body style="margin:0;padding:32px 12px;background:#e7e4da;">
       <div style="max-width:560px;margin:0 auto;background:#f6f5f0;border:1.5px solid #17160f;">
         <div style="background:#17160f;padding:26px 32px;">
           <h1 style="margin:0;font-family:'Helvetica Neue',Arial,sans-serif;font-weight:700;
                      font-size:28px;letter-spacing:-.02em;text-transform:uppercase;color:#f6f5f0;">
             <span style="color:#3b38f5;">&raquo;</span>Forward Pass<span style="color:#ff5a1f;">.</span></h1>
         </div>
         <div style="padding:28px 32px;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
                     font-size:15px;line-height:1.6;color:#3f3d33;">
           <p style="margin:0 0 12px;"><b>You're in — thanks for subscribing.</b></p>
           <p style="margin:0 0 12px;">Every Monday you'll get the week's top papers on tabular AI.</p>
           <p style="margin:0 0 18px;">Until then, catch up on what you've missed:</p>
           <a href="${site}/" style="display:inline-block;background:#3b38f5;color:#fff;
              font-family:ui-monospace,Menlo,monospace;font-size:12px;font-weight:600;
              letter-spacing:.05em;text-transform:uppercase;text-decoration:none;
              padding:10px 16px;">Read past issues</a>
         </div>
         <div style="background:#17160f;padding:22px 32px;text-align:center;">
           <span style="font-family:'Helvetica Neue',Arial,sans-serif;font-weight:700;font-size:20px;
                        text-transform:uppercase;color:#f6f5f0;">
             <span style="color:#3b38f5;">&raquo;</span>FP<span style="color:#ff5a1f;">.</span></span>
           <div style="margin-top:10px;font-family:ui-monospace,Menlo,monospace;font-size:10.5px;
                       color:#8f8c80;">Forward Pass is an AI-assisted newsletter and therefore it can
                       make mistakes. Check the linked papers.</div>
           <div style="margin-top:6px;font-family:ui-monospace,Menlo,monospace;font-size:10.5px;
                       color:#8f8c80;">New issue every Monday &middot;
             <a href="${unsubUrl}" style="color:#8f8c80;text-decoration:underline;">Unsubscribe</a></div>
         </div>
       </div></body>`;

    const raw = [
      `From: Forward Pass <${env.SMTP_USER}>`,
      `To: ${email}`,
      // RFC 2047 encoded-word: header charsets are separate from the body's,
      // so a bare UTF-8 em-dash here renders as mojibake in Gmail.
      `Subject: =?UTF-8?B?${b64Std("Welcome to Forward Pass — see you Monday")}?=`,
      `List-Unsubscribe: <${unsubUrl}>, <mailto:${env.SMTP_USER}?subject=unsubscribe>`,
      "List-Unsubscribe-Post: List-Unsubscribe=One-Click",
      "MIME-Version: 1.0",
      "Content-Type: text/html; charset=utf-8",
      "",
      html,
    ].join("\r\n");
    await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
      method: "POST",
      headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
      body: JSON.stringify({ raw: b64urlEncode(raw) }),
    });
  } catch { /* best-effort */ }
}

async function subscribe(req, env, url) {
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
  if (create.ok) {
    await sendWelcome(env, email, url.origin);  // brand-new subscriber
    return json({ ok: true }, 200, env);
  }

  // Already a contact: re-activate. Welcome them back only if they had
  // actually unsubscribed — a duplicate form submission stays silent.
  const lookup = await resend(env, "GET", `/contacts/${email}`);
  if (lookup.ok) {
    const contact = await lookup.json().catch(() => ({}));
    const wasUnsubscribed = !!(contact.unsubscribed ?? contact.data?.unsubscribed);
    const update = await resend(env, "PATCH", `/contacts/${email}`,
      { unsubscribed: false });
    if (update.ok) {
      if (wasUnsubscribed) await sendWelcome(env, email, url.origin);
      return json({ ok: true }, 200, env);
    }
  }

  // Surface Resend's own error so misconfigurations (e.g. an API key
  // without Full access) are diagnosable instead of a blind 502.
  const detail = await create.text().catch(() => "");
  return json({
    ok: false,
    error: "could not subscribe, try again later",
    detail: `resend ${create.status}: ${detail.slice(0, 300)}`,
  }, 502, env);
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
    // Deploy marker: lets the repo owner verify which build is live.
    if (url.pathname === "/version") {
      return json({ version: 6, welcome: true, gmail: !!env.GMAIL_REFRESH_TOKEN }, 200, env);
    }
    if (url.pathname === "/subscribe" && req.method === "POST") return subscribe(req, env, url);
    if (url.pathname === "/unsubscribe") return unsubscribe(req, env, url);
    return new Response("Not found", { status: 404, headers: cors(env) });
  },
};
