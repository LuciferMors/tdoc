"""Archive determinism — the headline guarantee of the spec.

Spec Part Two: "given identical inputs, two independent AXON encoders
must produce byte-for-byte identical archives."

This is required for:
  - cryptographic verification (the archive itself is the signed object)
  - deduplication in document management systems

If this test fails, the spec is a lie. Fix the encoder, don't weaken the test.
"""

import hashlib
import time
import zipfile


from axon import (
    convert_axc_string,
    encode_archive,
)


def _build_doc():
    axc = """
@section [id="intro"]:
  @heading [level=1]:
    Introduction
  @paragraph:
    A deterministic encoder produces byte-identical output for identical inputs.
  @paragraph:
    That property is testable.
""".strip()
    return convert_axc_string(
        axc,
        title="Determinism Test",
        document_type="article.test",
        authors=[{"name": "Test", "role": "author"}],
    )


def _sha(path: str) -> str:
    return hashlib.sha3_256(open(path, "rb").read()).hexdigest()


def test_encode_twice_same_bytes(tmp_path):
    """Two encodes of the same AxonDocument must yield byte-identical archives."""
    doc = _build_doc()
    # Pin all time-sensitive manifest fields so the caller's contract is clear.
    doc.manifest.created = "2024-01-01T00:00:00Z"
    doc.manifest.modified = "2024-01-01T00:00:00Z"
    doc.manifest.document_id = "01890000-0000-7000-8000-000000000000"

    p1 = tmp_path / "a.axon"
    p2 = tmp_path / "b.axon"
    encode_archive(doc, str(p1))
    # Force measurable real-time delta — if the encoder silently stamps current time,
    # this sleep makes the bug visible.
    time.sleep(1.1)
    # Re-pin in case the encoder mutated them on the first encode.
    doc.manifest.modified = "2024-01-01T00:00:00Z"
    encode_archive(doc, str(p2))

    assert _sha(p1) == _sha(p2), (
        "encode_archive produced non-deterministic bytes. "
        "Common causes: (a) manifest.modified bumped to utcnow() on encode, "
        "(b) ZIP entries stamped with current time, (c) signature includes a nonce/time."
    )


def test_zip_entry_timestamps_fixed(tmp_path):
    """ZIP entry dates must be fixed, not current time, for deterministic builds."""
    doc = _build_doc()
    doc.manifest.created = "2024-01-01T00:00:00Z"
    doc.manifest.modified = "2024-01-01T00:00:00Z"
    out = tmp_path / "x.axon"
    encode_archive(doc, str(out))
    with zipfile.ZipFile(out) as zf:
        dates = {info.filename: info.date_time for info in zf.infolist()}
    # Any entry whose date_time is "around now" (year == current year) fails determinism.
    # The deterministic convention is either the ZIP epoch (1980, 1, 1, 0, 0, 0) or a
    # fixed project-chosen date — anything OTHER than current wall time.
    import datetime as _dt

    now_year = _dt.datetime.now(_dt.timezone.utc).year
    offenders = [name for name, dt in dates.items() if dt[0] == now_year]
    assert not offenders, (
        f"ZIP entries stamped with current year ({now_year}): {offenders}. "
        "Use zipfile.ZipInfo(date_time=(1980,1,1,0,0,0)) or similar fixed epoch."
    )


def test_manifest_modified_not_bumped_on_encode(tmp_path):
    """encode_archive must not silently mutate manifest.modified to current time.

    Whether the timestamp is bumped should be the caller's decision — not a side
    effect that breaks the determinism contract.
    """
    doc = _build_doc()
    pinned = "2024-01-01T00:00:00Z"
    doc.manifest.created = pinned
    doc.manifest.modified = pinned
    out = tmp_path / "m.axon"
    encode_archive(doc, str(out))
    assert doc.manifest.modified == pinned, (
        f"encode_archive mutated manifest.modified from {pinned!r} to "
        f"{doc.manifest.modified!r}. Callers cannot rely on deterministic output."
    )
