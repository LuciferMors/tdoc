"""AXC parse/serialise round-trip invariants.

Spec Part Four: AXC must be reconstructable from plain text in a single pass.
The round-trip property is the test of that guarantee.
"""

from axon import parse_axc, serialize_axc


def _count(node):
    return 1 + sum(_count(c) for c in node.children)


def _normalise(s: str) -> str:
    # Round-trip equality is checked after stripping trailing whitespace
    # on each line — the parser is whitespace-insensitive at line ends.
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


def test_simple_paragraph_roundtrip():
    src = """
@document:
  @paragraph:
    Hello world.
""".strip()
    once = serialize_axc(parse_axc(src))
    twice = serialize_axc(parse_axc(once))
    assert _normalise(once) == _normalise(twice)


def test_nested_sections_roundtrip():
    src = """
@section [id="a"]:
  @heading [level=1]:
    Alpha
  @section [id="a.1"]:
    @heading [level=2]:
      Alpha one
    @paragraph:
      Inner paragraph.
""".strip()
    t1 = parse_axc(src)
    s1 = serialize_axc(t1)
    t2 = parse_axc(s1)
    s2 = serialize_axc(t2)
    assert _normalise(s1) == _normalise(s2)
    assert _count(t1) == _count(t2)


def test_attributes_preserved():
    src = """
@cell [data-type="pvalue" data-value="0.018" scope="row"]: 0.018
""".strip()
    t = parse_axc(src)
    cell = t.children[0] if t.type == "document" or t.children else t
    # The parser may wrap the single node in an implicit document;
    # walk to the actual @cell regardless.
    while cell.type != "cell" and cell.children:
        cell = cell.children[0]
    assert cell.attributes.get("data-type") == "pvalue"
    assert cell.attributes.get("data-value") == "0.018"
    assert cell.attributes.get("scope") == "row"


def test_unicode_content_roundtrip():
    src = """
@paragraph:
  Phase coherence α=0.05, β=0.80 — with en-dash and 中文.
""".strip()
    s1 = serialize_axc(parse_axc(src))
    s2 = serialize_axc(parse_axc(s1))
    assert _normalise(s1) == _normalise(s2)
    assert "中文" in s1
    assert "α" in s1


def test_demo_sample_roundtrip():
    """Exercises the full demo sample: sections, equations, tables, callouts, references."""
    src = r"""
@section [id="abstract"]:
  @heading [level=1]:
    Abstract
  @paragraph:
    Three mechanistically connected findings on FHRUC coupling.

@section [id="methods"]:
  @heading [level=1]:
    Methods
  @equation [id="eq-1" label="Phase Coherence"]:
    @latex:
      C(t) = \left| \frac{1}{N} \sum e^{i \Delta\phi} \right|
    @description:
      Magnitude of the mean complex exponential.

@section [id="results"]:
  @heading [level=1]:
    Results
  @table [id="tbl-main"]:
    @thead:
      @row:
        @cell [scope="col"]: Group
        @cell [scope="col"]: n
    @tbody:
      @row:
        @cell: Normal
        @cell [data-type="number"]: 347
      @row:
        @cell: Severe
        @cell [data-type="number"]: 25
  @callout [severity="minor"]:
    Permutation-validated.
""".strip()
    t1 = parse_axc(src)
    s1 = serialize_axc(t1)
    t2 = parse_axc(s1)
    s2 = serialize_axc(t2)
    # Content-preserving and idempotent under re-serialisation.
    assert _normalise(s1) == _normalise(s2)
    assert _count(t1) == _count(t2)
