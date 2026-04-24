// tdoc Cloudflare Worker — reverse-proxy api.tdoc.xyz/* → HF Space.
//
// Why: Hugging Face free Spaces don't allow custom domains. This Worker binds
// api.tdoc.xyz to an hf.space backend without exposing the HF URL to clients.
//
// Free tier: 100,000 requests/day, no credit card required.

// The origin we proxy to. If the HF Space URL changes (new name, owner, etc.),
// update this constant — it's the only place it should appear.
const ORIGIN = "https://LuciferMors-tdoc.hf.space";

// Headers that should NOT be forwarded either direction. Cloudflare strips
// most of these automatically but we're explicit for defence-in-depth.
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "te",
  "trailer",
  "upgrade",
  "proxy-authorization",
  "proxy-authenticate",
  // Don't let the origin set its own CORS — we control that here.
  "access-control-allow-origin",
  "access-control-allow-methods",
  "access-control-allow-headers",
  "access-control-expose-headers",
  "access-control-allow-credentials",
  "access-control-max-age",
]);

function stripHopByHop(headers) {
  const out = new Headers();
  for (const [k, v] of headers) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) out.set(k, v);
  }
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Block anything that isn't /v1/* or /docs or /openapi.json.
    // Anything else returns 404 at the edge — the origin never sees it.
    const path = url.pathname;
    const isAllowed =
      path === "/" ||
      path === "/docs" ||
      path === "/redoc" ||
      path === "/openapi.json" ||
      path.startsWith("/v1/");
    if (!isAllowed) {
      return new Response("Not Found", { status: 404 });
    }

    // Rewrite target URL. Preserve path + query, swap host.
    const targetUrl = new URL(path + url.search, ORIGIN);

    // Preserve method + body + relevant headers.
    const originReq = new Request(targetUrl.toString(), {
      method: request.method,
      headers: stripHopByHop(request.headers),
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : request.body,
      redirect: "manual",
    });

    // Set Host and a marker header so the origin can tell this came through us.
    originReq.headers.set("Host", new URL(ORIGIN).host);
    originReq.headers.set("X-Forwarded-Proto", "https");
    originReq.headers.set("X-Forwarded-Host", url.host);
    originReq.headers.set("X-Forwarded-For", request.headers.get("CF-Connecting-IP") || "");
    originReq.headers.set("X-TDoc-Proxy", "cf-worker");

    let resp;
    try {
      resp = await fetch(originReq);
    } catch (err) {
      return new Response(
        JSON.stringify({
          error: "upstream_unreachable",
          detail: "The tdoc API backend is temporarily unreachable. Retry in a moment.",
        }),
        {
          status: 502,
          headers: { "content-type": "application/json" },
        },
      );
    }

    // Strip the origin's response hop-by-hop / CORS headers, then set ours.
    const respHeaders = stripHopByHop(resp.headers);

    // CORS — production defaults. Widen only as needed.
    respHeaders.set("Access-Control-Allow-Origin", "*");
    respHeaders.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    respHeaders.set(
      "Access-Control-Allow-Headers",
      "Authorization, Content-Type, X-Request-ID",
    );
    respHeaders.set("Access-Control-Max-Age", "3600");

    // Preserve the A+ header stack we earned on the apex.
    respHeaders.set(
      "Strict-Transport-Security",
      "max-age=31536000; includeSubDomains; preload",
    );
    respHeaders.set("X-Content-Type-Options", "nosniff");
    respHeaders.set("X-Frame-Options", "DENY");
    respHeaders.set("Referrer-Policy", "strict-origin-when-cross-origin");

    return new Response(resp.body, {
      status: resp.status,
      statusText: resp.statusText,
      headers: respHeaders,
    });
  },
};
