/**
 * @tdoc/sdk — Official TypeScript SDK for the tdoc.xyz API.
 *
 * Wraps every v1 endpoint with a typed, ergonomic surface:
 *
 *   const tdoc = new TdocClient({ apiKey: process.env.TDOC_API_KEY! });
 *   const result = await tdoc.structure(file);
 *   console.log(result.tree);
 *
 * Works in Node 18+ and modern browsers (uses `fetch` + `FormData` + `Blob`).
 * No transitive dependencies.
 */

export const SDK_VERSION = "0.1.0";

/** AXON tree node — every node has a type and may carry attributes,
 *  text, and children. Mirrors the wire format of the API's `tree` field. */
export interface AxonNode {
  type: string;
  attributes?: Record<string, string>;
  text?: string;
  children?: AxonNode[];
}

/** Response shape for /v1/structure and /v1/try-public.
 *  Five views of the same document; pick whichever your application needs. */
export interface StructureResponse {
  document_id: string;
  content_hash: string;
  render_hash: string;
  axc: string;
  nodes: number;
  warnings: string[];
  /** Rendered HTML — preview-quality, journal-style typography. */
  html: string;
  /** AXON tree as a JSON object — every LLM tool can ingest this directly. */
  tree: AxonNode;
  /** Base64 of the deterministic .tdoc archive (ZIP). */
  archive_b64: string;
  /** Base64 of a real PDF that opens in any viewer, with the AXON tree
   *  embedded inside as PDF/A-3-style attachments. */
  pdf_b64: string;
}

export interface QueryResponse {
  count: number;
  results: Array<Record<string, unknown> | string>;
}

export interface PlanInfo {
  plan: "free" | "pro" | "team" | "scale";
  units_used: number;
  units_included: number;
  overage_price_cents: number;
}

export interface Signature {
  type: string;
  signature: string;
  public_key: string;
  covered_fields: string[];
}

export interface SignResponse { signature: Signature; }
export interface VerifyResponse { valid: boolean; }

/** Errors returned by the API after the 4xx/5xx is surfaced. */
export class TdocApiError extends Error {
  readonly status: number;
  readonly requestId?: string;
  readonly detail?: string;
  constructor(status: number, message: string, opts?: { requestId?: string; detail?: string }) {
    super(message);
    this.name = "TdocApiError";
    this.status = status;
    if (opts?.requestId) this.requestId = opts.requestId;
    if (opts?.detail) this.detail = opts.detail;
  }
}

export interface TdocClientOptions {
  /** Bearer API key. Get one by emailing hello@tdoc.xyz during beta. */
  apiKey?: string;
  /** Defaults to https://api.tdoc.xyz */
  baseUrl?: string;
  /** Custom fetch impl — for testing or non-standard environments. */
  fetch?: typeof fetch;
  /** Request timeout in milliseconds. Default: 60_000. */
  timeoutMs?: number;
}

const DEFAULT_BASE = "https://api.tdoc.xyz";

/** Browser-friendly file argument: a Blob, a File, or a Node-style
 *  { data: Uint8Array; filename: string; type?: string }. */
export type FileArg =
  | Blob
  | File
  | { data: Uint8Array; filename: string; type?: string };

function toBlob(arg: FileArg, fallbackName = "upload"): { blob: Blob; name: string } {
  if (typeof File !== "undefined" && arg instanceof File) {
    return { blob: arg, name: arg.name };
  }
  if (arg instanceof Blob) {
    return { blob: arg, name: fallbackName };
  }
  const o = arg as { data: Uint8Array; filename: string; type?: string };
  return {
    blob: new Blob([o.data], { type: o.type || "application/octet-stream" }),
    name: o.filename || fallbackName,
  };
}

export class TdocClient {
  private readonly apiKey: string | undefined;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(opts: TdocClientOptions = {}) {
    this.apiKey = opts.apiKey;
    this.baseUrl = (opts.baseUrl || DEFAULT_BASE).replace(/\/$/, "");
    this.fetchImpl = opts.fetch || globalThis.fetch.bind(globalThis);
    this.timeoutMs = opts.timeoutMs ?? 60_000;
  }

  /** Liveness probe. No auth required. */
  async healthz(): Promise<{ ok: boolean; version: string }> {
    return this.json("/v1/healthz", { method: "GET", auth: false });
  }

  /** Caller identity + current usage + quota. Auth required. */
  async me(): Promise<PlanInfo> {
    return this.json("/v1/me", { method: "GET", auth: true });
  }

  /** Convert a PDF / .axc / .txt / .md / .tdoc upload into an AXON tree.
   *  Authenticated path — counts against your plan's units. */
  async structure(
    file: FileArg,
    opts: { title?: string; documentType?: string } = {},
  ): Promise<StructureResponse> {
    const { blob, name } = toBlob(file, "in.bin");
    const fd = new FormData();
    fd.append("file", blob, name);
    if (opts.title) fd.append("title", opts.title);
    if (opts.documentType) fd.append("document_type", opts.documentType);
    return this.json("/v1/structure", { method: "POST", body: fd, auth: true });
  }

  /** Same response shape as `structure`, no auth, 5 MiB demo cap.
   *  Powers the public /try page. Use for demos and free-tier integrations. */
  async tryPublic(
    file: FileArg,
    opts: { title?: string; documentType?: string } = {},
  ): Promise<StructureResponse> {
    const { blob, name } = toBlob(file, "demo.bin");
    const fd = new FormData();
    fd.append("file", blob, name);
    if (opts.title) fd.append("title", opts.title);
    if (opts.documentType) fd.append("document_type", opts.documentType);
    return this.json("/v1/try-public", { method: "POST", body: fd, auth: false });
  }

  /** Run an AQL query over an AXON document. Auth required. */
  async query(aql: string, axc: string): Promise<QueryResponse> {
    return this.json("/v1/query", {
      method: "POST",
      body: { aql, axc },
      auth: true,
    });
  }

  /** Ed25519-sign an AXON document with the server's signing key.
   *  Available on Team and Scale tiers. */
  async sign(
    args: { axc: string; render_axr?: string; manifest: Record<string, unknown> },
  ): Promise<SignResponse> {
    return this.json("/v1/sign", {
      method: "POST",
      body: { axc: args.axc, render_axr: args.render_axr ?? "", manifest: args.manifest },
      auth: true,
    });
  }

  /** Verify a previously-signed AXON document. Returns { valid: true|false }. */
  async verify(
    args: {
      axc: string;
      render_axr?: string;
      manifest: Record<string, unknown>;
      signature: Signature;
    },
  ): Promise<VerifyResponse> {
    return this.json("/v1/verify", {
      method: "POST",
      body: {
        axc: args.axc,
        render_axr: args.render_axr ?? "",
        manifest: args.manifest,
        signature: args.signature,
      },
      auth: true,
    });
  }

  /** Convenience: decode the response's PDF (with embedded AXON) into a Blob
   *  suitable for browser download or direct write. */
  static pdfBlob(resp: StructureResponse): Blob {
    return new Blob([base64ToBytes(resp.pdf_b64)], { type: "application/pdf" });
  }

  /** Convenience: decode the response's .tdoc archive into a Blob. */
  static archiveBlob(resp: StructureResponse): Blob {
    return new Blob([base64ToBytes(resp.archive_b64)], { type: "application/zip" });
  }

  // ─── internals ────────────────────────────────────────────────

  private async json<T>(
    path: string,
    opts: { method: "GET" | "POST"; body?: unknown; auth: boolean },
  ): Promise<T> {
    const url = this.baseUrl + path;
    const headers: Record<string, string> = { "X-Lib": `tdoc-ts/${SDK_VERSION}` };
    let body: BodyInit | undefined;

    if (opts.body instanceof FormData) {
      body = opts.body;
    } else if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    if (opts.auth) {
      if (!this.apiKey) {
        throw new TdocApiError(0, "API key required for " + path);
      }
      headers["Authorization"] = "Bearer " + this.apiKey;
    }

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        method: opts.method,
        headers,
        body,
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    const reqId = res.headers.get("x-request-id") || undefined;
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = (await res.json()) as { detail?: string; error?: string };
        detail = data?.detail || data?.error;
      } catch {
        try { detail = await res.text(); } catch { /* ignore */ }
      }
      throw new TdocApiError(
        res.status,
        `HTTP ${res.status} on ${path}${detail ? " — " + detail : ""}`,
        reqId !== undefined ? { requestId: reqId, detail } : { detail },
      );
    }
    return (await res.json()) as T;
  }
}

/** base64 → Uint8Array — pure JS, no Node `Buffer` dependency. */
function base64ToBytes(b64: string): Uint8Array {
  const bin =
    typeof atob === "function"
      ? atob(b64)
      : Buffer.from(b64, "base64").toString("binary");
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
