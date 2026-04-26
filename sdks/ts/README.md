# @tdoc/sdk

Official TypeScript / JavaScript SDK for [tdoc.xyz](https://tdoc.xyz) — the typed-document API.

Convert PDFs into AXON trees, render journal-grade HTML/PDF, query typed cells with AQL, sign + verify documents with Ed25519. Same five-format response surface as `/try` (axc / html / json tree / .tdoc archive / .pdf with embedded AXON).

```ts
import { TdocClient } from "@tdoc/sdk";

const tdoc = new TdocClient({ apiKey: process.env.TDOC_API_KEY! });

// Upload a PDF, get five formats back.
const file = new File([await Bun.file("paper.pdf").arrayBuffer()], "paper.pdf");
const r = await tdoc.structure(file);

console.log(r.tree);                  // structured JSON for AI agents
console.log(r.html.slice(0, 200));    // journal-style preview
await Bun.write("paper.tdoc.pdf", TdocClient.pdfBlob(r));
```

## Install

```sh
npm install @tdoc/sdk
# or
pnpm add @tdoc/sdk
# or
bun add @tdoc/sdk
```

Requires Node 18+ or any modern browser (uses `fetch`, `FormData`, `Blob`).

## Quick reference

```ts
const tdoc = new TdocClient({ apiKey: "tdoc_..." });

await tdoc.healthz();                                  // {ok:true, version:"0.1.0"}
await tdoc.me();                                       // plan, units used / included
await tdoc.structure(file);                            // PDF/.axc/.txt/.md/.tdoc → 5 formats
await tdoc.tryPublic(file);                            // anonymous demo, 5 MiB cap
await tdoc.query(aql, axc);                            // AQL query over a tree
await tdoc.sign({ axc, manifest });                    // Ed25519 sign (Team+ tier)
await tdoc.verify({ axc, manifest, signature });       // verify a signed doc
```

## Browser usage

The SDK is browser-safe — no Node-only APIs. Bundle it with your tool of choice:

```ts
import { TdocClient } from "@tdoc/sdk";

document.querySelector("input[type=file]")!.addEventListener("change", async (e) => {
  const f = (e.target as HTMLInputElement).files![0];
  const r = await new TdocClient({ apiKey: KEY }).structure(f);
  document.querySelector("#preview")!.innerHTML = r.html;
});
```

## Errors

Every non-2xx response throws a `TdocApiError`:

```ts
import { TdocApiError } from "@tdoc/sdk";

try {
  await tdoc.structure(file);
} catch (err) {
  if (err instanceof TdocApiError) {
    console.error(err.status, err.detail, err.requestId);
  } else {
    throw err;
  }
}
```

## Types

Every endpoint is fully typed; pull `StructureResponse`, `QueryResponse`, `Signature`, `PlanInfo`, `AxonNode` from the package root.

## License

Apache-2.0. Contribute at [github.com/LuciferMors/tdoc](https://github.com/LuciferMors/tdoc).
