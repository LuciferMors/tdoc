"""AXON v1.1 — semantic research-document extensions.

Locks in parser, renderer, and validator behaviour for the seven new
node types: @finding, @hypothesis, @result, @metric, @narrative,
@code_ref, @link, @view.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from axon import (  # noqa: E402
    AxonDocument,
    convert_axc_string,
    parse_axc,
    render_html,
    serialize_axc,
    validate,
)


def _doc_with_axc(axc_text: str, doc_type: str = "preprint") -> AxonDocument:
    return convert_axc_string(axc_text, title="t11", document_type=doc_type)


# ─── @finding ───────────────────────────────────────────────────


def test_finding_renders_with_data_attrs_for_ai_extraction():
    axc = (
        "@finding [type=primary significance=0.005 validated=permutation]:\n"
        "  Severe-state coherence is elevated relative to controls.\n"
    )
    doc = _doc_with_axc(axc)
    html = render_html(doc)
    assert 'class="finding finding--primary"' in html
    assert 'data-finding-type="primary"' in html
    assert 'data-significance="0.005"' in html
    assert 'data-validated="permutation"' in html
    assert "Severe-state coherence" in html


def test_finding_warns_when_attrs_missing():
    axc = "@finding:\n  bare claim\n"
    result = validate(_doc_with_axc(axc))
    assert any("@finding missing type" in w for w in result.warnings)
    assert any("@finding missing significance" in w for w in result.warnings)


# ─── @hypothesis ────────────────────────────────────────────────


def test_hypothesis_renders_with_status_class():
    axc = "@hypothesis [id=H1 status=supported]:\n  Stage 3 sleep predicts coherence.\n"
    html = render_html(_doc_with_axc(axc))
    assert "hypothesis--supported" in html
    assert 'data-hypothesis-id="H1"' in html
    assert 'data-hypothesis-status="supported"' in html


def test_hypothesis_warns_on_nonstandard_status():
    axc = "@hypothesis [id=H1 status=banana]:\n  …\n"
    warns = validate(_doc_with_axc(axc)).warnings
    assert any("non-standard" in w for w in warns)


# ─── @result + @metric (data binding) ───────────────────────────


def test_result_emits_data_attrs_and_dl():
    axc = (
        "@result [metric=phase_coherence method=mann_whitney severe=0.349 "
        "normal=0.250 p_value=0.005]:\n"
        "  Severe vs normal cohorts.\n"
    )
    html = render_html(_doc_with_axc(axc))
    assert 'data-metric="phase_coherence"' in html
    assert 'data-method="mann_whitney"' in html
    assert 'data-severe="0.349"' in html
    assert 'data-p_value="0.005"' in html
    # The dl renders both keys and values for the human reader.
    assert "<dt>severe</dt>" in html
    assert "<dd " in html and "0.349" in html


def test_result_warns_when_metric_missing():
    axc = "@result [severe=0.3]:\n"
    assert any(
        "@result missing metric" in w for w in validate(_doc_with_axc(axc)).warnings
    )


def test_metric_carries_machine_readable_attrs():
    axc = "@metric [name=mass value=28.4 unit=g group=treated]:\n"
    html = render_html(_doc_with_axc(axc))
    assert 'data-metric-name="mass"' in html
    assert 'data-metric-value="28.4"' in html
    assert 'data-metric-unit="g"' in html


# ─── @narrative ────────────────────────────────────────────────


def test_narrative_role_class_and_data_attr():
    axc = (
        "@narrative [role=motivation]:\n"
        "  PDFs lose semantic ground truth as soon as they're rendered.\n"
    )
    html = render_html(_doc_with_axc(axc))
    assert "narrative--motivation" in html
    assert 'data-narrative-role="motivation"' in html
    assert "PDFs lose semantic ground truth" in html


def test_narrative_warns_when_role_missing():
    axc = "@narrative:\n  …\n"
    assert any(
        "@narrative missing role" in w for w in validate(_doc_with_axc(axc)).warnings
    )


# ─── @code_ref (reproducibility hook) ───────────────────────────


def test_code_ref_renders_repo_link_and_repro_badge():
    axc = (
        "@code_ref [repo=github.com/me/proj script=analysis.py "
        "commit=abc1234 reproducible=true]:\n"
    )
    html = render_html(_doc_with_axc(axc))
    assert 'data-repo="github.com/me/proj"' in html
    assert 'data-script="analysis.py"' in html
    assert 'data-commit="abc1234"' in html
    assert 'data-reproducible="true"' in html
    assert "reproducible" in html
    assert "github.com/me/proj" in html


def test_code_ref_warns_when_repo_missing():
    axc = "@code_ref [script=foo.py]:\n"
    assert any(
        "@code_ref missing repo" in w for w in validate(_doc_with_axc(axc)).warnings
    )


# ─── @link (cross-reference, knowledge graph) ───────────────────


def test_link_renders_from_to_type_attrs():
    axc = "@link [from=H1 to=R3 type=validated_by]:\n"
    html = render_html(_doc_with_axc(axc))
    assert 'data-link-from="H1"' in html
    assert 'data-link-to="R3"' in html
    assert 'data-link-type="validated_by"' in html
    # Human-readable label maps the type to natural English.
    assert "validated by" in html


def test_link_warns_when_endpoints_missing():
    axc = "@link [type=related]:\n"
    warns = validate(_doc_with_axc(axc)).warnings
    assert any("@link missing from" in w for w in warns)


# ─── @view (multi-view declaration) ─────────────────────────────


def test_view_emits_meta_block_and_validates():
    axc = "@view [type=summary]:\n@view [type=graph]:\n@view [type=linear]:\n"
    doc = _doc_with_axc(axc)
    html = render_html(doc)
    # All three declarations land as <meta class="axon-view"> blocks.
    assert html.count('class="axon-view"') == 3
    assert 'data-view-type="summary"' in html
    assert 'data-view-type="graph"' in html
    assert 'data-view-type="linear"' in html
    # Standard types validate without warnings.
    assert all("non-standard" not in w for w in validate(doc).warnings if "@view" in w)


def test_view_warns_on_nonstandard_type():
    axc = "@view [type=hologram]:\n"
    warns = validate(_doc_with_axc(axc)).warnings
    assert any("@view type='hologram' is non-standard" in w for w in warns)


# ─── Roundtrip: serialize and re-parse keeps every v1.1 attribute ──


def test_v11_roundtrip_preserves_attrs():
    axc = (
        "@finding [significance=0.001 type=primary validated=bootstrap]:\n"
        "  primary outcome\n"
        "@hypothesis [id=H1 status=supported]:\n"
        "  hypothesis text\n"
        "@result [metric=hr method=cox p=0.001 hr=0.61]:\n"
        "@metric [name=duration value=987 unit=days]:\n"
        "@narrative [role=clinical_implication]:\n"
        "  what it means in clinic\n"
        "@code_ref [repo=github.com/owner/repo script=run.py reproducible=true]:\n"
        "@link [from=H1 to=R1 type=validated_by]:\n"
        "@view [type=summary]:\n"
    )
    doc = _doc_with_axc(axc)
    serialized = serialize_axc(doc.content)
    reparsed = parse_axc(serialized)
    # Compare at the to_dict level — bypasses any Node identity oddities.
    assert doc.content.to_dict() == reparsed.to_dict()
