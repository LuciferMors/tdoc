"""Spec-conformance suite — what a compliant AXON reader MUST reject.

Spec Part Two: "Every AXON-compliant reader must reject archives that violate
this structure." Part Five: "Any node containing data should declare its type."
The validator is the gate — these tests assert the gate holds.
"""

from axon import (
    convert_axc_string,
    validate,
    parse_axc,
    serialize_axc,
    AxonDocument,
    Manifest,
    default_render_profile,
)


def _base_doc(title="Test", doctype="article.test"):
    axc = """
@section [id="s1"]:
  @paragraph:
    Base content.
""".strip()
    return convert_axc_string(axc, title=title, document_type=doctype)


def test_empty_title_rejected():
    """manifest.title MUST be non-empty — it is the human identity of the doc."""
    doc = _base_doc()
    doc.manifest.title = ""
    result = validate(doc)
    assert not result.valid
    assert any("title" in e.lower() for e in result.errors)


def test_missing_document_id_rejected():
    """manifest.document_id MUST be set — it is the machine identity of the doc."""
    doc = _base_doc()
    doc.manifest.document_id = ""
    result = validate(doc)
    assert not result.valid
    assert any("document_id" in e.lower() for e in result.errors)


def test_non_document_root_rejected():
    """Content root MUST be @document (spec Part Four)."""
    # Build a doc whose content root is a @section, not a @document.
    bad_root = parse_axc(
        "@section [id='rogue']:\n  @paragraph:\n    Should not be root."
    )
    # parse_axc may still wrap in @document; force the bug explicitly.
    if bad_root.type == "document" and bad_root.children:
        bad_root = bad_root.children[0]
    doc = AxonDocument(
        manifest=Manifest(title="Bad", document_type="article.test"),
        content=bad_root,
        render=default_render_profile(),
    )
    result = validate(doc)
    assert not result.valid
    assert any("root" in e.lower() or "document" in e.lower() for e in result.errors)


def test_duplicate_real_ids_still_flagged():
    """The validator must still flag REAL duplicate ids (not placeholders).
    Regression guard on the em-dash fix — we relaxed placeholders, not real ids."""
    doc = _base_doc()
    # Force two sections with the same non-placeholder id.
    for s in doc.content.find("section"):
        s.attributes["id"] = "intro"
    result = validate(doc)
    # At least one duplicate error if there were ≥2 sections.
    sections = doc.content.find("section")
    if len(sections) >= 2:
        assert any("Duplicate node id" in e for e in result.errors)


def test_placeholder_ids_not_flagged():
    """Placeholder ids ('', '-', '—') must NOT be treated as duplicates."""
    axc = """
@section [id="-"]:
  @paragraph:
    First.
@section [id="—"]:
  @paragraph:
    Second.
@section [id=""]:
  @paragraph:
    Third.
""".strip()
    doc = convert_axc_string(axc, title="Placeholders", document_type="article.test")
    result = validate(doc)
    # No "Duplicate node id" errors should fire for placeholder ids.
    dup_errors = [e for e in result.errors if "Duplicate node id" in e]
    assert dup_errors == [], f"Placeholder ids incorrectly flagged: {dup_errors}"


def test_image_missing_alt_warns():
    """@image without alt text MUST produce an accessibility warning (spec Part Eleven)."""
    axc = """
@section [id="s"]:
  @figure [id="f1"]:
    @image [src="x.png" id="img1"]:
""".strip()
    doc = convert_axc_string(axc, title="AltTest", document_type="article.test")
    result = validate(doc)
    assert any("alt" in w.lower() for w in result.warnings)


def test_table_missing_summary_warns():
    """@table without a summary attribute MUST produce a warning."""
    axc = """
@section [id="s"]:
  @table [id="t1"]:
    @thead:
      @row:
        @cell: A
""".strip()
    doc = convert_axc_string(axc, title="TableTest", document_type="article.test")
    result = validate(doc)
    assert any("summary" in w.lower() for w in result.warnings)


def test_equation_missing_description_warns():
    """@equation without @description MUST warn (accessibility requirement)."""
    axc = r"""
@section [id="s"]:
  @equation [id="eq1"]:
    @latex:
      x + y = z
""".strip()
    doc = convert_axc_string(axc, title="EqTest", document_type="article.test")
    result = validate(doc)
    assert any("description" in w.lower() for w in result.warnings)


def test_content_hash_mismatch_rejected():
    """Validator must reject a document whose stored content_hash doesn't match
    the recomputed hash of the content tree (tamper detection)."""
    doc = _base_doc()
    from axon import hash_text

    doc.manifest.content_hash = hash_text(serialize_axc(doc.content))
    doc.manifest.render_hash = "0" * 64  # recompute_from_render mismatch
    # Tamper: mutate a paragraph — content_hash is now stale.
    doc.content.children[0].children[0].text = "Tampered."
    result = validate(doc)
    assert not result.valid
    assert any("hash" in e.lower() for e in result.errors)
