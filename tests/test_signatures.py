"""Signature / integrity tests.

Current axon.sign_document is a hash-integrity record, not a cryptographic
signature — the comment in axon.py itself says so. These tests establish:

  1. Content-hash verification rejects post-hoc tampering (the weak guarantee).
  2. A proper Ed25519-based signer is still missing (xfail to make the gap visible).

The xfail is the TODO beacon for the next phase.
"""

import pytest

from axon import (
    convert_axc_string,
    encode_archive,
    decode_archive,
    validate,
    verify_document,
    serialize_axc,
    serialize_axr,
)


def _doc():
    axc = """
@section [id="s"]:
  @paragraph:
    Signed content.
""".strip()
    return convert_axc_string(axc, title="Sig Test", document_type="article.test")


def test_content_hash_detects_content_modification(tmp_path):
    doc = _doc()
    path = tmp_path / "d.axon"
    encode_archive(doc, str(path))
    loaded = decode_archive(str(path), verify=True)

    # Round-trip OK.
    assert validate(loaded).valid

    # Tamper the content: the manifest hash no longer matches the content bytes.
    loaded.content.children[0].children[0].text = "Tampered content."
    # validate() recomputes hash from serialized content and compares to manifest.
    result = validate(loaded)
    assert not result.valid, "validator accepted tampered content"
    assert any(
        "hash" in e.lower() for e in result.errors
    ), f"validator didn't flag hash mismatch; errors: {result.errors}"


def test_manifest_hash_tamper_detected():
    doc = _doc()
    content_axc = serialize_axc(doc.content)
    render_axr = serialize_axr(doc.render)
    # Corrupt the manifest content_hash; verify_document must fail.
    doc.manifest.content_hash = "0" * 64
    assert not verify_document(
        doc, content_axc, render_axr
    ), "verify_document accepted a manifest with a zeroed content_hash"


def test_ed25519_sign_and_verify():
    pytest.importorskip("cryptography")
    from axon import sign_document_ed25519, verify_document_ed25519
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()

    doc = _doc()
    content_axc = serialize_axc(doc.content)
    render_axr = serialize_axr(doc.render)
    manifest_dict = doc.manifest.to_dict()

    sig = sign_document_ed25519(content_axc, render_axr, manifest_dict, sk)
    assert sig["type"] == "ed25519"
    assert len(bytes.fromhex(sig["signature"])) == 64  # Ed25519 signatures are 64 bytes
    assert (
        len(bytes.fromhex(sig["public_key"])) == 32
    )  # Ed25519 public keys are 32 bytes

    # Valid path.
    assert verify_document_ed25519(content_axc, render_axr, manifest_dict, sig, pk)
    # Embedded-key path (no explicit pk).
    assert verify_document_ed25519(content_axc, render_axr, manifest_dict, sig)

    # Tamper: flip a byte of content → signature must fail.
    tampered = content_axc.replace("Signed", "Forged", 1)
    assert not verify_document_ed25519(tampered, render_axr, manifest_dict, sig, pk)

    # Tamper: modify manifest → signature must fail.
    tampered_manifest = {**manifest_dict, "title": "Different Title"}
    assert not verify_document_ed25519(
        content_axc, render_axr, tampered_manifest, sig, pk
    )


def test_ed25519_deterministic():
    """Ed25519 has no nonce — signing the same payload with the same key twice
    must produce identical signatures (determinism contract)."""
    pytest.importorskip("cryptography")
    from axon import sign_document_ed25519
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    doc = _doc()
    content_axc = serialize_axc(doc.content)
    render_axr = serialize_axr(doc.render)
    manifest_dict = doc.manifest.to_dict()

    sig1 = sign_document_ed25519(content_axc, render_axr, manifest_dict, sk)
    sig2 = sign_document_ed25519(content_axc, render_axr, manifest_dict, sk)
    assert sig1 == sig2
