// Smoke test — does not hit the live API. Exercises the client's request
// shaping (auth header, FormData, JSON body, error paths) against a fake
// fetch and pins the contracts that production depends on.

import { test } from "node:test";
import assert from "node:assert/strict";
import { TdocClient, TdocApiError } from "../dist/index.mjs";

function fakeFetch(handler) {
  return async (url, init) => {
    const r = await handler(url, init);
    return new Response(
      typeof r.body === "string" ? r.body : JSON.stringify(r.body ?? {}),
      {
        status: r.status ?? 200,
        headers: { "content-type": "application/json", ...r.headers },
      },
    );
  };
}

test("healthz: no auth, GET, parses body", async () => {
  const calls = [];
  const tdoc = new TdocClient({
    fetch: fakeFetch((url, init) => {
      calls.push({ url, init });
      return { body: { ok: true, version: "0.1.0" } };
    }),
  });
  const r = await tdoc.healthz();
  assert.equal(r.ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers.Authorization, undefined);
});

test("me: auth required — throws if no key", async () => {
  const tdoc = new TdocClient({
    fetch: fakeFetch(() => ({ body: {} })),
  });
  await assert.rejects(() => tdoc.me(), TdocApiError);
});

test("me: with key — Bearer header set", async () => {
  let captured;
  const tdoc = new TdocClient({
    apiKey: "tdoc_test_key",
    fetch: fakeFetch((url, init) => {
      captured = init;
      return { body: { plan: "team", units_used: 0, units_included: 10000, overage_price_cents: 2 } };
    }),
  });
  const r = await tdoc.me();
  assert.equal(r.plan, "team");
  assert.equal(captured.headers.Authorization, "Bearer tdoc_test_key");
});

test("structure: builds FormData and POSTs", async () => {
  let captured;
  const tdoc = new TdocClient({
    apiKey: "k",
    fetch: fakeFetch((url, init) => {
      captured = { url, init };
      return {
        body: {
          document_id: "x",
          content_hash: "h",
          render_hash: "h",
          axc: "@p:\n  hi",
          nodes: 1,
          warnings: [],
          html: "<p>hi</p>",
          tree: { type: "document" },
          archive_b64: "",
          pdf_b64: "",
        },
      };
    }),
  });
  await tdoc.structure(
    { data: new Uint8Array([1, 2, 3]), filename: "x.axc" },
    { title: "T", documentType: "preprint" },
  );
  assert.match(captured.url, /\/v1\/structure$/);
  assert.equal(captured.init.method, "POST");
  // FormData carries multipart bytes — content-type set by fetch automatically.
  assert.equal(typeof captured.init.body, "object");
});

test("4xx response surfaces as TdocApiError with detail + requestId", async () => {
  const tdoc = new TdocClient({
    apiKey: "k",
    fetch: async () =>
      new Response(JSON.stringify({ detail: "Demo limit is 5 MiB." }), {
        status: 413,
        headers: { "content-type": "application/json", "x-request-id": "abc123" },
      }),
  });
  try {
    await tdoc.tryPublic({ data: new Uint8Array(10), filename: "big.txt" });
    assert.fail("should have thrown");
  } catch (err) {
    assert.ok(err instanceof TdocApiError);
    assert.equal(err.status, 413);
    assert.equal(err.requestId, "abc123");
    assert.match(err.detail, /5 MiB/);
  }
});

test("static helpers: pdfBlob + archiveBlob decode base64", () => {
  // 'PK' = 0x50 0x4b — ZIP magic. base64('PK') = 'UEs='.
  const pdf = TdocClient.pdfBlob({ pdf_b64: "UEs=" });
  const arc = TdocClient.archiveBlob({ archive_b64: "UEs=" });
  assert.equal(pdf.size, 2);
  assert.equal(arc.size, 2);
  assert.equal(pdf.type, "application/pdf");
  assert.equal(arc.type, "application/zip");
});
