#!/usr/bin/env python3
"""
AXON System Demo
================
Demonstrates the complete pipeline:
  1. Convert the uploaded JSON-SDF pipeline output → .axon archive
  2. Validate the archive
  3. Render to HTML and plain text
  4. Run AQL queries
  5. Show diff between two documents
  6. Build a document from scratch using AXC notation
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from axon import (
    AxonDocument,
    Node,
    convert_json_sdf,
    convert_axc_string,
    encode_archive,
    decode_archive,
    validate,
    render_html,
    render_text,
    execute_aql,
    diff_trees,
    serialize_delta,
    hash_text,
    parse_axc,
    serialize_axc,
)

OUTPUT_DIR = os.environ.get(
    "AXON_DEMO_OUT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_out"),
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

JSON_SDF_INPUT = os.environ.get("AXON_DEMO_JSON_SDF")


# ──────────────────────────────────────────────
# DEMO 1: Convert JSON-SDF to AXON
# ──────────────────────────────────────────────


def demo_json_to_axon():
    print("\n" + "=" * 60)
    print("DEMO 1: JSON-SDF Pipeline Output → AXON Archive")
    print("=" * 60)

    if not JSON_SDF_INPUT or not os.path.exists(JSON_SDF_INPUT):
        print("  SKIPPED: set AXON_DEMO_JSON_SDF=/path/to/input.json to run this demo.")
        return None

    output_path = f"{OUTPUT_DIR}/fhr_paper.axon"

    doc = convert_json_sdf(
        JSON_SDF_INPUT,
        title="FHR-UC Phase Hypercoupling in Fetal Acidosis",
        document_type="article.research",
    )
    doc.manifest.authors = [
        {"name": "Demo Author", "role": "author", "identifier": "author@example.com"}
    ]
    doc.manifest.language = "en"
    doc.manifest.license = "CC-BY-4.0"

    # Add a pre-declared AQL query
    doc.queries["all_definitions"] = """QUERY all_definitions
FROM @definition
SELECT data-type, text
RETURNS list"""

    encode_archive(doc, output_path)
    print(f"  Created: {output_path}")
    print(f"  Title:   {doc.manifest.title}")
    print(f"  Nodes:   {_count_nodes(doc.content)}")
    return output_path


# ──────────────────────────────────────────────
# DEMO 2: Build from scratch with AXC notation
# ──────────────────────────────────────────────


def demo_axc_from_scratch():
    print("\n" + "=" * 60)
    print("DEMO 2: Build Document from AXC Notation (Research Paper)")
    print("=" * 60)

    axc = """
@section [id="abstract"]:
  @heading [level=1]:
    Abstract
  @paragraph:
    This study reports three mechanistically connected findings
    regarding FHRUC phase coupling in intrapartum labour.
    Fetuses destined for severe acidosis show elevated
    FHRUC phase coherence in the first 20 minutes of labour,
    confirmed by permutation testing (n=506).

@section [id="methods"]:
  @heading [level=1]:
    Methods
  @paragraph:
    We analysed 506 intrapartum CTG recordings from the
    CTU-UHB Intrapartum CTG Database. Instantaneous phase
    coherence between FHR and UC was computed using the
    Hilbert transform in sliding 5-minute windows.
  @equation [id="eq-coherence" label="Phase Coherence"]:
    @latex:
      C(t) = \\left| \\frac{1}{N} \\sum_{k=1}^{N} e^{i \\Delta\\phi(t,k)} \\right|
    @description:
      Phase coherence C at time t is the magnitude of the mean
      complex exponential of instantaneous phase differences,
      summed over N samples. Values range from 0 to 1.
    @notation_definitions:
      C(t): Phase coherence at window t, bounded 0 to 1.
      N: Number of samples in the window.

@section [id="results"]:
  @heading [level=1]:
    Results
  @paragraph:
    Fetuses with severe acidosis exhibited significantly elevated
    FHRUC phase coherence in the first 20 minutes.
  @table [id="tbl-main" summary="Early FHRUC phase coherence by neonatal outcome group"]:
    @thead:
      @row:
        @cell [scope=col]: Group
        @cell [scope=col]: n
        @cell [scope=col]: Median Coherence
        @cell [scope=col]: p-value
    @tbody:
      @row:
        @cell: Normal (pH >= 7.20)
        @cell [data-type=number]: 347
        @cell [data-type=ratio data-value=0.250]: 0.250
        @cell [data-type=pvalue data-value=0.000]: —
      @row:
        @cell: Severe (pH < 7.05)
        @cell [data-type=number]: 25
        @cell [data-type=ratio data-value=0.336]: 0.336
        @cell [data-type=pvalue data-value=0.018]: 0.018
  @callout [severity=minor]:
    Permutation-validated: minute 12 p=0.005, minute 18 p=0.012.

@section [id="conclusions"]:
  @heading [level=1]:
    Conclusions
  @paragraph:
    Early-labour FHRUC phase hypercoupling in fetuses destined
    for severe acidosis represents a mechanistic signature of
    compensatory autonomic activation. Coherence above 0.45
    carries a 5.8x relative risk of severe acidosis.

@section [id="references" role=references]:
  @heading [level=1]:
    References
  @reference [id="chudacek2014" type=journal-article]:
    @authors:
      @person: Chudacek, Vaclav
      @person: Spilka, Jiri
    @title:
      Open access intrapartum CTG database
    @journal: BMC Pregnancy and Childbirth
    @year: 2014
    @doi: 10.1186/1471-2393-14-16
"""

    doc = convert_axc_string(
        axc,
        title="FHR-UC Phase Hypercoupling in Fetal Acidosis",
        document_type="article.research",
        authors=[{"name": "Demo Author", "role": "author"}],
    )

    output_path = f"{OUTPUT_DIR}/paper_native.axon"
    encode_archive(doc, output_path)
    print(f"  Created: {output_path}")
    print(f"  Sections: {len(doc.content.find('section'))}")
    print(f"  Equations: {len(doc.content.find('equation'))}")
    print(f"  Tables: {len(doc.content.find('table'))}")
    return doc, output_path


# ──────────────────────────────────────────────
# DEMO 3: Validation
# ──────────────────────────────────────────────


def demo_validate(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 3: Validation Engine")
    print("=" * 60)
    result = validate(doc)
    print(result)


# ──────────────────────────────────────────────
# DEMO 4: HTML Rendering
# ──────────────────────────────────────────────


def demo_render_html(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 4: HTML Renderer")
    print("=" * 60)
    html = render_html(doc)
    path = f"{OUTPUT_DIR}/paper.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written: {path}")
    print(f"  Size: {len(html):,} bytes")
    print("  Preview (first 300 chars of body):")
    start = html.find("<body>") + 6
    print("  " + html[start : start + 300].replace("\n", " ").strip())
    return path


# ──────────────────────────────────────────────
# DEMO 5: Plain-text Rendering
# ──────────────────────────────────────────────


def demo_render_text(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 5: Plain-Text Renderer")
    print("=" * 60)
    text = render_text(doc)
    path = f"{OUTPUT_DIR}/paper.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Written: {path}")
    lines = text.splitlines()
    print(f"  Lines: {len(lines)}")
    print("\n  --- OUTPUT PREVIEW ---")
    for line in lines[:40]:
        print(f"  {line}")
    print("  --- END PREVIEW ---")


# ──────────────────────────────────────────────
# DEMO 6: AQL Queries
# ──────────────────────────────────────────────


def demo_queries(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 6: AQL Query Engine")
    print("=" * 60)

    queries = {
        "all_p_values": """QUERY all_p_values
FROM @cell [data-type=pvalue]
SELECT data-value, text
RETURNS list""",
        "significant_p_values": """QUERY significant_p_values
FROM @cell [data-type=pvalue]
SELECT data-value, text
WHERE data-value < 0.05
RETURNS list""",
        "all_equations": """QUERY all_equations
FROM @equation
SELECT id, label
RETURNS list""",
        "ratio_cells": """QUERY ratio_cells
FROM @cell [data-type=ratio]
SELECT data-value, text
ORDER BY data-value DESC
RETURNS list""",
    }

    for qname, aql in queries.items():
        result = execute_aql(aql, doc.content)
        if "error" in result:
            print(f"\n  Query: {qname}  ERROR: {result['error']}")
            continue
        print(f"\n  Query: {qname}")
        print(f"  Found: {result['count']} result(s)")
        for row in result["results"][:5]:
            print(f"    {row}")


# ──────────────────────────────────────────────
# DEMO 7: Diff Engine
# ──────────────────────────────────────────────


def demo_diff(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 7: Diff Engine (AXD)")
    print("=" * 60)

    # Create a modified version of the document
    import copy

    doc2 = copy.deepcopy(doc)

    # Modify: change a paragraph text
    paras = doc2.content.find("paragraph")
    if paras:
        paras[0].text = (
            paras[0].text + " [REVISED: Additional context added by reviewer.]"
        )
        paras[0].attributes["id"] = "para-revised-001"

    # Add a new section
    new_section = parse_axc("""
@section [id="discussion"]:
  @heading [level=1]:
    Discussion
  @paragraph:
    The findings are consistent with a compensatory autonomic
    hyperactivation model in fetuses with pre-existing compromise.
""")
    for child in new_section.children:
        doc2.content.children.append(child)

    ops = diff_trees(doc.content, doc2.content)
    print(f"  Operations: {len(ops)}")
    for op in ops[:10]:
        print(f"    {op.op:15s}  id={op.target_id}")

    delta = serialize_delta(
        ops=ops,
        delta_id=2,
        parent_revision=1,
        author="reviewer@example.com",
        summary="Added revised paragraph and discussion section",
        parent_content_hash=doc.manifest.content_hash,
        resulting_content_hash=hash_text(serialize_axc(doc2.content)),
    )
    doc2.manifest.revision = 2
    doc2.deltas = [delta]
    path = f"{OUTPUT_DIR}/paper_revised.axon"
    encode_archive(doc2, path)
    print(f"  Saved revised version: {path}")
    print("  Delta stored in archive history/")


# ──────────────────────────────────────────────
# DEMO 8: Round-trip Integrity
# ──────────────────────────────────────────────


def demo_roundtrip(path: str):
    print("\n" + "=" * 60)
    print("DEMO 8: Archive Round-trip and Integrity Verification")
    print("=" * 60)

    doc = decode_archive(path, verify=True)
    print(f"  Loaded and verified: {path}")
    print(f"  Title:           {doc.manifest.title}")
    print(f"  Content hash:    {doc.manifest.content_hash[:32]}...")
    print(f"  Render hash:     {doc.manifest.render_hash[:32]}...")
    print("  Integrity:       PASS (hashes match)")

    # Test tampering detection
    print("\n  Simulating tamper detection...")
    doc.manifest.content_hash = "0" * 64
    result = validate(doc)
    print(f"  Tampered hash detected: {'YES' if not result.valid else 'NO'}")
    for e in result.errors:
        if "hash" in e.lower():
            print(f"    Error: {e}")


# ──────────────────────────────────────────────
# DEMO 9: AXC serialization round-trip
# ──────────────────────────────────────────────


def demo_axc_roundtrip(doc: AxonDocument):
    print("\n" + "=" * 60)
    print("DEMO 9: AXC Parser/Serialiser Round-trip")
    print("=" * 60)

    axc1 = serialize_axc(doc.content)
    parsed = parse_axc(axc1)
    axc2 = serialize_axc(parsed)

    nodes1 = _count_nodes(doc.content)
    nodes2 = _count_nodes(parsed)

    print(f"  Original AXC: {len(axc1):,} bytes, {nodes1} nodes")
    print(f"  Re-serialised: {len(axc2):,} bytes, {nodes2} nodes")
    print(f"  Content identical: {axc1.strip() == axc2.strip()}")

    # Save AXC for inspection
    path = f"{OUTPUT_DIR}/paper.axc"
    with open(path, "w", encoding="utf-8") as f:
        f.write(axc1)
    print(f"  AXC saved: {path}")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _count_nodes(root: Node) -> int:
    return 1 + sum(_count_nodes(c) for c in root.children)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("AXON Document Format — Complete System Demo")
    print("============================================")

    # Demo 1: Convert pipeline JSON to AXON (skipped unless AXON_DEMO_JSON_SDF set)
    demo_json_to_axon()

    # Demo 2: Build from AXC scratch
    doc, native_path = demo_axc_from_scratch()

    # Demo 3: Validate
    demo_validate(doc)

    # Demo 4: HTML render
    html_path = demo_render_html(doc)

    # Demo 5: Plain-text render
    demo_render_text(doc)

    # Demo 6: Queries
    demo_queries(doc)

    # Demo 7: Diff
    demo_diff(doc)

    # Demo 8: Round-trip integrity
    demo_roundtrip(native_path)

    # Demo 9: AXC round-trip
    demo_axc_roundtrip(doc)

    print("\n" + "=" * 60)
    print("ALL DEMOS COMPLETE")
    print("=" * 60)
    print("\nOutput files:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(f"{OUTPUT_DIR}/{f}")
        print(f"  {f:<35s}  {size:>10,} bytes")
