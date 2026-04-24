"""Decode-side safety: ZIP-bomb and path-traversal defenses.

Any .axon archive read by decode_archive() is untrusted until proven otherwise.
These tests construct adversarial ZIPs and assert that each class of attack is
rejected with AxonSecurityError — not with a generic crash and not with silent
memory exhaustion.
"""

import os
import zipfile

import pytest

from axon import (
    AxonSecurityError,
    decode_archive,
)


def _write_archive(tmp_path, entries, name="adv.axon"):
    """Write a ZIP archive containing the given (arcname, bytes) entries."""
    out = tmp_path / name
    with zipfile.ZipFile(out, "w") as zf:
        for arcname, data in entries:
            zf.writestr(arcname, data)
    return out


def test_reject_path_traversal(tmp_path):
    """An entry with a '..' segment must be rejected."""
    path = _write_archive(
        tmp_path,
        [
            ("../etc/passwd", b"malicious"),
            ("manifest.json", b"{}"),
        ],
    )
    with pytest.raises(AxonSecurityError, match="parent traversal"):
        decode_archive(str(path), verify=False)


def test_reject_absolute_entry_name(tmp_path):
    """An entry with an absolute path must be rejected."""
    path = _write_archive(
        tmp_path,
        [
            ("/etc/passwd", b"malicious"),
            ("manifest.json", b"{}"),
        ],
    )
    with pytest.raises(AxonSecurityError, match="absolute"):
        decode_archive(str(path), verify=False)


def test_reject_zip_bomb_by_ratio(tmp_path):
    """A single highly-compressible entry above the ratio threshold is rejected.

    1 MiB of null bytes compresses to a few KiB — ratio >> 200 → bomb.
    """
    payload = b"\x00" * (1 * 1024 * 1024)  # 1 MiB of zeros
    path = tmp_path / "bomb.axon"
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        zf.writestr("bomb.dat", payload)
    with pytest.raises(AxonSecurityError, match="ZIP bomb|compression ratio"):
        decode_archive(str(path), verify=False, max_compression_ratio=200)


def test_reject_oversized_member(tmp_path):
    """A single entry exceeding max_member_bytes is rejected."""
    # 256 KiB payload, but we set max_member_bytes=1024 → reject.
    path = _write_archive(
        tmp_path,
        [
            ("big.bin", b"A" * (256 * 1024)),
        ],
    )
    with pytest.raises(AxonSecurityError, match="max_member_bytes"):
        decode_archive(str(path), verify=False, max_member_bytes=1024)


def test_reject_oversized_archive(tmp_path):
    """An archive whose on-disk size exceeds max_archive_bytes is rejected
    before any entry is even inspected."""
    path = _write_archive(tmp_path, [("x", b"hello")])
    size = os.path.getsize(path)
    with pytest.raises(AxonSecurityError, match="max_archive_bytes"):
        decode_archive(str(path), verify=False, max_archive_bytes=size - 1)


def test_legitimate_archive_still_decodes(tmp_path):
    """The hardening must not regress legitimate round-trip: encode→decode succeeds."""
    from axon import convert_axc_string, encode_archive

    axc = """
@section [id="ok"]:
  @paragraph:
    A legitimate document should decode without issue.
""".strip()
    doc = convert_axc_string(axc, title="OK", document_type="article.test")
    out = tmp_path / "legit.axon"
    encode_archive(doc, str(out))

    loaded = decode_archive(str(out), verify=True)
    assert loaded.manifest.title == "OK"
