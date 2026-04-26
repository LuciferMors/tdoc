#!/usr/bin/env python3
"""
AXON Document Format — Complete Reference Implementation v1.0
=============================================================
Sections:
  1   Constants and type registry
  2   Data model
  3   AXC parser  (text → node tree)
  4   AXC serialiser (node tree → text)
  5   AXR render profile parser
  6   Manifest and metadata
  7   Cryptographic integrity (SHA3-256 + optional Ed25519)
  8   Archive encoder  (node tree → .axon zip)
  9   Archive decoder  (.axon zip → node tree)
  10  Validation engine
  11  HTML renderer
  12  Plain-text renderer
  13  PDF converter  (requires PyMuPDF)
  14  JSON-SDF converter  (pipeline JSON → AXON)
  15  AQL query engine
  16  Diff engine  (AXD delta notation)
  17  CLI
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import textwrap
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────
# SECTION 1 — CONSTANTS AND TYPE REGISTRY
# ─────────────────────────────────────────────────────────────

AXON_VERSION = "1.1"

BLOCK_TYPES = {
    "document",
    "section",
    "heading",
    "paragraph",
    "list",
    "item",
    "table",
    "thead",
    "tbody",
    "row",
    "cell",
    "figure",
    "image",
    "caption",
    "equation",
    "latex",
    "description",
    "notation_definitions",
    "code",
    "blockquote",
    "definition",
    "footnote",
    "aside",
    "callout",
    "data",
    "component",
    "static_fallback",
    "component_config",
    "include",
    "annotation_zone",
    "reference",
    "authors",
    "person",
    "title",
    "journal",
    "volume",
    "issue",
    "pages",
    "year",
    "doi",
    "pmid",
    "url",
    "access_date",
    "reading_order",
    "conflict",
    "abstract",
    "keywords",
    "highlight",
    "data_source",
}

INLINE_TYPES = {
    "em",
    "strong",
    "cite",
    "link",
    "abbr",
    "math",
    "code",
    "mark",
    "note",
    "data",
    "lang",
    "time",
}

DATA_TYPES = {
    "text",
    "number",
    "measure",
    "pvalue",
    "percentage",
    "ratio",
    "boolean",
    "date",
    "datetime",
    "duration",
    "identifier",
    "currency",
    "coordinate",
    "classification",
    "range",
    "formula",
    "reference",
    "uncertain",
}

DOCUMENT_TYPES = {
    "article.research",
    "article.review",
    "article.editorial",
    "article.case-report",
    "report.technical",
    "report.institutional",
    "report.audit",
    "legal.contract",
    "legal.legislation",
    "legal.ruling",
    "legal.filing",
    "book.monograph",
    "book.chapter",
    "book.textbook",
    "correspondence.letter",
    "correspondence.memo",
    "correspondence.email",
    "specification",
    "dataset",
    "protocol",
    "patent",
    "preprint",
}

RENDER_PROFILES = {"default", "screen", "print", "braille", "audio", "minimal"}

REQUIRED_SECTIONS_BY_TYPE = {
    "article.research": {"introduction", "methods", "results", "discussion"},
    "article.review": {"introduction", "methods", "conclusions"},
    "preprint": set(),
}

# ─────────────────────────────────────────────────────────────
# SECTION 2 — DATA MODEL
# ─────────────────────────────────────────────────────────────


@dataclass
class Node:
    """Universal node in the AXON content tree."""

    type: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List["Node"] = field(default_factory=list)
    text: str = ""
    _parent: Optional["Node"] = field(default=None, compare=False, repr=False)

    def get(self, attr: str, default: Any = None) -> Any:
        return self.attributes.get(attr, default)

    def find(self, node_type: str) -> List["Node"]:
        """Depth-first search for nodes of a given type."""
        results = []
        if self.type == node_type:
            results.append(self)
        for child in self.children:
            results.extend(child.find(node_type))
        return results

    def find_one(self, node_type: str) -> Optional["Node"]:
        r = self.find(node_type)
        return r[0] if r else None

    def find_by_id(self, node_id: str) -> Optional["Node"]:
        if self.attributes.get("id") == node_id:
            return self
        for child in self.children:
            result = child.find_by_id(node_id)
            if result:
                return result
        return None

    def text_content(self) -> str:
        """Recursively extract all text content."""
        parts = [self.text] if self.text else []
        for child in self.children:
            parts.append(child.text_content())
        return " ".join(p for p in parts if p).strip()

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.attributes:
            d["attributes"] = self.attributes
        if self.text:
            d["text"] = self.text
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class InlineSpan:
    """Represents <<type attrs>>content<</type>> inside text."""

    type: str
    attributes: Dict[str, str] = field(default_factory=dict)
    content: str = ""


@dataclass
class Manifest:
    axon_version: str = AXON_VERSION
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_type: str = "article.research"
    title: str = ""
    language: str = "en"
    created: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )
    modified: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )
    revision: int = 1
    content_hash: str = ""
    render_hash: str = ""
    dependencies: List[dict] = field(default_factory=list)
    authors: List[dict] = field(default_factory=list)
    license: str = "CC-BY-4.0"
    render_profiles: List[str] = field(default_factory=lambda: ["default"])
    native_axon: bool = True
    conversion_tool: Optional[str] = None
    accessibility: dict = field(
        default_factory=lambda: {
            "alt_text_coverage": 1.0,
            "reading_order_declared": False,
            "language_switches_marked": False,
        }
    )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        return {k: v for k, v in sorted(d.items()) if v is not None}


@dataclass
class RenderRule:
    name: str
    target_type: str
    target_attrs: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class RenderProfile:
    name: str
    rules: List[RenderRule] = field(default_factory=list)

    def get_rules_for(self, node: Node) -> List[RenderRule]:
        matched = []
        for rule in self.rules:
            if rule.target_type == node.type:
                attr_match = all(
                    node.attributes.get(k) == v for k, v in rule.target_attrs.items()
                )
                if attr_match:
                    matched.append(rule)
        return matched

    def get_property(self, node: Node, prop: str, default: str = "") -> str:
        for rule in reversed(self.get_rules_for(node)):
            if prop in rule.properties:
                return rule.properties[prop]
        return default


@dataclass
class AxonDocument:
    manifest: Manifest
    content: Node
    render: RenderProfile
    metadata: dict = field(default_factory=dict)
    deltas: List[dict] = field(default_factory=list)
    annotations: List[dict] = field(default_factory=list)
    signatures: List[dict] = field(default_factory=list)
    queries: Dict[str, str] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# SECTION 3 — AXC PARSER
# ─────────────────────────────────────────────────────────────

_NODE_DECL = re.compile(
    r"^(?P<indent>\s*)@(?P<type>\w+)(?:\s*\[(?P<attrs>[^\]]*)\])?\s*:?\s*(?P<inline>[^@].*)?\s*$"
)
_ATTR_PAIR = re.compile(r'(\w[\w-]*)=(?:"([^"]*?)"|\'([^\']*?)\'|(\S+))')
_INLINE_OPEN = re.compile(r"<<(\w+)(?:\s+([^>]*))?>>(.+?)<</\1>>")


def _parse_attrs(attr_str: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    if not attr_str:
        return attrs
    for m in _ATTR_PAIR.finditer(attr_str):
        key = m.group(1)
        val = m.group(2) or m.group(3) or m.group(4) or ""
        attrs[key] = val
    return attrs


def _indent_level(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_axc(text: str) -> Node:
    """Parse AXC content notation into a Node tree."""
    lines = text.expandtabs(2).splitlines()
    root = Node(type="document")
    stack: List[Tuple[int, Node]] = [(-1, root)]

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.rstrip()
        if not stripped.strip():
            i += 1
            continue

        indent = _indent_level(stripped)
        m = _NODE_DECL.match(stripped)

        if m:
            node_type = m.group("type")
            attrs = _parse_attrs(m.group("attrs") or "")
            inline_text = (m.group("inline") or "").strip()
            node = Node(type=node_type, attributes=attrs, text=inline_text)

            # Pop stack to the right parent level
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()

            parent = stack[-1][1]
            parent.children.append(node)
            node._parent = parent
            stack.append((indent, node))

        else:
            # Text content line — belongs to current node
            content = stripped.strip()
            if stack:
                current = stack[-1][1]
                if current.text:
                    current.text += " " + content
                else:
                    current.text = content

        i += 1

    return root


def parse_inline(text: str) -> List[Any]:
    """Parse inline spans from text, returning mixed list of str and InlineSpan."""
    parts: List[Any] = []
    last = 0
    for m in _INLINE_OPEN.finditer(text):
        if m.start() > last:
            parts.append(text[last : m.start()])
        span_type = m.group(1)
        attrs = _parse_attrs(m.group(2) or "")
        content = m.group(3)
        parts.append(InlineSpan(type=span_type, attributes=attrs, content=content))
        last = m.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


# ─────────────────────────────────────────────────────────────
# SECTION 4 — AXC SERIALISER
# ─────────────────────────────────────────────────────────────


def _serialize_attrs(attrs: Dict[str, str]) -> str:
    if not attrs:
        return ""
    parts = []
    for k, v in sorted(attrs.items()):
        if " " in v:
            parts.append(f'{k}="{v}"')
        else:
            parts.append(f"{k}={v}")
    return "[" + " ".join(parts) + "]"


def serialize_axc(node: Node, indent: int = 0) -> str:
    """Serialise a Node tree to AXC content notation."""
    lines: List[str] = []
    pad = "  " * indent

    if node.type == "document":
        # Root document node: serialise children directly
        for child in node.children:
            lines.append(serialize_axc(child, indent))
        return "\n".join(lines)

    attr_str = _serialize_attrs(node.attributes)
    decl = f"{pad}@{node.type}"
    if attr_str:
        decl += f" {attr_str}"
    decl += ":"

    lines.append(decl)

    if node.text:
        # Word-wrap text content at 80 chars
        inner_pad = "  " * (indent + 1)
        wrapped = textwrap.fill(
            node.text,
            width=80,
            initial_indent=inner_pad,
            subsequent_indent=inner_pad,
        )
        lines.append(wrapped)

    for child in node.children:
        lines.append(serialize_axc(child, indent + 1))

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SECTION 5 — AXR RENDER PROFILE PARSER
# ─────────────────────────────────────────────────────────────

_RULE_BLOCK = re.compile(r"(\w[\w-]*)\s*\{([^}]*)\}", re.DOTALL)
_PROP_LINE = re.compile(r"([\w-]+)\s*:\s*(.+)")


def parse_axr(text: str) -> RenderProfile:
    """Parse AXR render notation into a RenderProfile."""
    rules: List[RenderRule] = []
    for m in _RULE_BLOCK.finditer(text):
        rule_name = m.group(1)
        body = m.group(2)
        props: Dict[str, str] = {}
        target_type = ""
        target_attrs: Dict[str, str] = {}
        for pm in _PROP_LINE.finditer(body):
            key = pm.group(1).strip()
            val = pm.group(2).strip().rstrip(";")
            if key == "target":
                # Parse target: node_type [attr=val ...]
                parts = val.split(None, 1)
                target_type = parts[0]
                if len(parts) > 1:
                    attr_s = parts[1].strip().strip("[]")
                    target_attrs = _parse_attrs(attr_s)
            else:
                props[key] = val
        if target_type:
            rules.append(
                RenderRule(
                    name=rule_name,
                    target_type=target_type,
                    target_attrs=target_attrs,
                    properties=props,
                )
            )
    return RenderProfile(name="parsed", rules=rules)


def default_render_profile() -> RenderProfile:
    rules = [
        RenderRule(
            "body-text",
            "paragraph",
            {},
            {
                "font-family": "Georgia",
                "font-size": "11pt",
                "line-height": "1.45",
                "margin-bottom": "0.8em",
            },
        ),
        RenderRule(
            "heading-1",
            "heading",
            {"level": "1"},
            {
                "font-family": "sans-serif",
                "font-size": "18pt",
                "font-weight": "700",
                "margin-top": "2em",
            },
        ),
        RenderRule(
            "heading-2",
            "heading",
            {"level": "2"},
            {
                "font-family": "sans-serif",
                "font-size": "14pt",
                "font-weight": "600",
                "margin-top": "1.8em",
            },
        ),
        RenderRule(
            "code-block",
            "code",
            {},
            {
                "font-family": "monospace",
                "background": "#f5f5f5",
                "padding": "1em",
            },
        ),
        RenderRule(
            "table-base",
            "table",
            {},
            {
                "border-collapse": "collapse",
                "width": "100%",
            },
        ),
        RenderRule(
            "cell-base",
            "cell",
            {},
            {
                "border": "1px solid #ccc",
                "padding": "0.4em 0.6em",
            },
        ),
    ]
    return RenderProfile(name="default", rules=rules)


def serialize_axr(profile: RenderProfile) -> str:
    lines = []
    for rule in profile.rules:
        lines.append(f"{rule.name} {{")
        # Build target string
        target = rule.target_type
        if rule.target_attrs:
            attr_parts = [f"{k}={v}" for k, v in sorted(rule.target_attrs.items())]
            target += " [" + " ".join(attr_parts) + "]"
        lines.append(f"  target: {target};")
        for k, v in sorted(rule.properties.items()):
            lines.append(f"  {k}: {v};")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SECTION 6 — MANIFEST AND METADATA
# ─────────────────────────────────────────────────────────────


def build_metadata(manifest: Manifest, extra: Optional[dict] = None) -> dict:
    base = {
        "dc:title": manifest.title,
        "dc:language": manifest.language,
        "dc:created": manifest.created,
        "dc:modified": manifest.modified,
        "dc:type": manifest.document_type,
        "dc:license": manifest.license,
    }
    for author in manifest.authors:
        base.setdefault("dc:creator", []).append(author.get("name", ""))
    if extra:
        base.update(extra)
    return dict(sorted(base.items()))


def build_provenance(manifest: Manifest) -> dict:
    return {
        "created_with": "axon-reference-implementation-v1.0",
        "native_axon": manifest.native_axon,
        "conversion_tool": manifest.conversion_tool,
        "revision": manifest.revision,
        "document_id": manifest.document_id,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 7 — CRYPTOGRAPHIC INTEGRITY
# ─────────────────────────────────────────────────────────────


def sha3_256(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


def hash_text(text: str) -> str:
    return sha3_256(text.encode("utf-8"))


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON serialisation: sorted keys, no extra whitespace."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def compute_document_hashes(
    content_axc: str,
    render_axr: str,
) -> Tuple[str, str]:
    return hash_text(content_axc), hash_text(render_axr)


def verify_document(doc: AxonDocument, content_axc: str, render_axr: str) -> bool:
    ch, rh = compute_document_hashes(content_axc, render_axr)
    return doc.manifest.content_hash == ch and doc.manifest.render_hash == rh


def _signing_payload(content_axc: str, render_axr: str, manifest_dict: dict) -> bytes:
    """Canonical bytes to be hashed and signed. Deterministic function of inputs."""
    return canonical_json(
        {
            "manifest": manifest_dict,
            "content_hash": hash_text(content_axc),
            "render_hash": hash_text(render_axr),
        }
    )


def sign_document(content_axc: str, render_axr: str, manifest_dict: dict) -> dict:
    """Create a deterministic integrity record (hash-based, not a cryptographic signature).

    The returned dict is a pure function of its inputs — it contains no wall-clock
    timestamp and no nonce. For true cryptographic signing, use sign_document_ed25519.
    """
    return {
        "type": "hash-integrity",
        "signed_hash": sha3_256(
            _signing_payload(content_axc, render_axr, manifest_dict)
        ),
        "algorithm": "SHA3-256",
    }


def sign_document_ed25519(
    content_axc: str,
    render_axr: str,
    manifest_dict: dict,
    private_key: Any,
) -> dict:
    """Create an Ed25519 signature over the document's canonical signing payload.

    Ed25519 is chosen because it is:
      - deterministic (no per-signature nonce — two signs of the same payload
        produce identical bytes, matching AXON's determinism contract),
      - small (64-byte signatures, 32-byte public keys),
      - widely implemented, with a formal security proof.

    Args:
        private_key: An Ed25519PrivateKey from cryptography.hazmat.

    Returns a signature dict serialisable to JSON. The public key is embedded so
    the signature is independently verifiable without side-channel key lookup.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires the optional 'cryptography' dependency. "
            "Install with: pip install 'axon-document[crypto]'"
        ) from exc

    payload = _signing_payload(content_axc, render_axr, manifest_dict)
    digest = sha3_256(payload).encode("ascii")
    signature_bytes = private_key.sign(digest)
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "type": "ed25519",
        "algorithm": "Ed25519 over SHA3-256",
        "public_key": pub_bytes.hex(),
        "signature": signature_bytes.hex(),
        "covered_fields": ["manifest", "content_hash", "render_hash"],
    }


def verify_document_ed25519(
    content_axc: str,
    render_axr: str,
    manifest_dict: dict,
    sig_dict: dict,
    public_key: Optional[Any] = None,
) -> bool:
    """Verify an Ed25519 signature over the document's canonical signing payload.

    If public_key is None, the key embedded in sig_dict is used — the caller
    is responsible for pinning / trusting that key through out-of-band means
    (e.g. a known key fingerprint in a trust store).

    Returns True iff the signature is valid for the exact inputs provided.
    Any mutation of content_axc, render_axr, or manifest_dict post-sign
    invalidates the signature.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ImportError(
            "Ed25519 verification requires the optional 'cryptography' dependency."
        ) from exc

    if sig_dict.get("type") != "ed25519":
        return False

    try:
        sig_bytes = bytes.fromhex(sig_dict["signature"])
        if public_key is None:
            pub_bytes = bytes.fromhex(sig_dict["public_key"])
            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        payload = _signing_payload(content_axc, render_axr, manifest_dict)
        digest = sha3_256(payload).encode("ascii")
        public_key.verify(sig_bytes, digest)
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False


# ─────────────────────────────────────────────────────────────
# SECTION 8 — ARCHIVE ENCODER
# ─────────────────────────────────────────────────────────────

# Fixed ZIP entry timestamp used for deterministic archive builds.
# 1980-01-01 00:00:00 is the ZIP format epoch — matches conventions used by
# reproducible-builds toolchains (Debian, pip wheels, etc.).
_AXON_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def encode_archive_to_bytes(doc: AxonDocument) -> bytes:
    """Encode an AxonDocument to a deterministic .tdoc archive in memory.

    Same byte-deterministic contract as encode_archive(); use this when you
    want the bytes directly (HTTP response, embedding in another archive)
    without going through the filesystem.
    """
    return _encode_archive_impl(doc)


def encode_archive(doc: AxonDocument, output_path: str) -> str:
    """Encode an AxonDocument to a deterministic .axon archive.

    Determinism contract (Spec Part Two):
      Given identical input state, two encodes produce byte-identical archives.

    To uphold it, this function:
      - does NOT mutate doc.manifest.modified — the caller owns that field,
      - stamps every ZIP entry with a fixed epoch (1980-01-01),
      - sorts entries by archive name before writing,
      - uses canonical JSON for all metadata (sorted keys, UTF-8, fixed indent),
      - excludes wall-clock timestamps from the hash-integrity signature.
    """
    data = _encode_archive_impl(doc)
    with open(output_path, "wb") as f:
        f.write(data)
    return output_path


def _encode_archive_impl(doc: AxonDocument) -> bytes:
    content_axc = serialize_axc(doc.content)
    render_axr = serialize_axr(doc.render)

    # Compute hashes (deterministic function of content/render bytes).
    ch, rh = compute_document_hashes(content_axc, render_axr)
    doc.manifest.content_hash = ch
    doc.manifest.render_hash = rh

    manifest_dict = doc.manifest.to_dict()
    metadata = build_metadata(doc.manifest, doc.metadata)
    provenance = build_provenance(doc.manifest)
    accessibility = {
        **doc.manifest.accessibility,
        "alt_text_coverage": _compute_alt_coverage(doc.content),
    }

    signature = sign_document(content_axc, render_axr, manifest_dict)

    # Collect all (arcname, bytes) pairs first so we can sort before writing.
    entries: List[Tuple[str, bytes]] = []

    def add_text(arcname: str, text: str) -> None:
        entries.append((arcname, text.encode("utf-8")))

    def add_json(arcname: str, obj: Any) -> None:
        add_text(arcname, json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False))

    add_json("manifest.json", manifest_dict)
    add_text("content/document.axc", content_axc)
    add_text("render/default.axr", render_axr)
    add_json("metadata/core.json", metadata)
    add_json("metadata/provenance.json", provenance)
    add_json("metadata/accessibility.json", accessibility)

    if doc.signatures or signature:
        sigs = doc.signatures + [signature]
        add_json("signatures/integrity.sig", sigs)

    for i, ann in enumerate(doc.annotations):
        add_json(f"annotations/set_{i:04d}.json", ann)

    for delta in doc.deltas:
        n = delta.get("delta_id", 0)
        add_json(f"history/delta_{n:04d}.axd", delta)

    for name in sorted(doc.queries):
        add_text(f"queries/{name}.aql", doc.queries[name])

    entries.sort(key=lambda e: e[0])

    buf = io.BytesIO()
    with zipfile.ZipFile(
        buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        for arcname, data in entries:
            info = zipfile.ZipInfo(filename=arcname, date_time=_AXON_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # fixed permissions for determinism
            zf.writestr(info, data, compresslevel=9)

    return buf.getvalue()


def _compute_alt_coverage(root: Node) -> float:
    images = root.find("image")
    if not images:
        return 1.0
    covered = sum(
        1 for img in images if img.attributes.get("alt") or img.find_one("alt")
    )
    return round(covered / len(images), 3)


# ─────────────────────────────────────────────────────────────
# SECTION 9 — ARCHIVE DECODER
# ─────────────────────────────────────────────────────────────

# Decode-side safety limits. These bound worst-case memory use when reading
# an untrusted .axon archive. Callers may override per-call via decode_archive().
AXON_DEFAULT_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024  # 256 MiB on-disk
AXON_DEFAULT_MAX_MEMBER_BYTES = 128 * 1024 * 1024  # 128 MiB per member
AXON_DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024  # 512 MiB total uncompressed
AXON_DEFAULT_MAX_RATIO = 200  # compressed → uncompressed ratio


class AxonSecurityError(ValueError):
    """Raised when a .axon archive violates a safety bound (ZIP bomb, path traversal, etc.)."""


def _safe_arcname(arcname: str) -> str:
    """Reject absolute or escaping arcnames; return a normalised safe form.

    Defenses: absolute paths, parent-directory segments, drive letters, backslashes.
    """
    if not arcname or arcname != arcname.strip():
        raise AxonSecurityError(
            f"archive entry name has leading/trailing whitespace: {arcname!r}"
        )
    if arcname.startswith(("/", "\\")) or (len(arcname) > 1 and arcname[1] == ":"):
        raise AxonSecurityError(f"archive entry name is absolute: {arcname!r}")
    # Normalise separators, then reject any ".." segment.
    parts = arcname.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise AxonSecurityError(
            f"archive entry name contains parent traversal: {arcname!r}"
        )
    return arcname


def decode_archive(
    path: str,
    verify: bool = True,
    *,
    max_archive_bytes: int = AXON_DEFAULT_MAX_ARCHIVE_BYTES,
    max_member_bytes: int = AXON_DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = AXON_DEFAULT_MAX_TOTAL_BYTES,
    max_compression_ratio: int = AXON_DEFAULT_MAX_RATIO,
) -> AxonDocument:
    """Decode a .axon archive to an AxonDocument.

    Safety checks (ZIP-bomb + path-traversal defense):
      - on-disk archive size must be <= max_archive_bytes
      - each entry's uncompressed size <= max_member_bytes
      - each entry's compression ratio <= max_compression_ratio
      - sum of all uncompressed sizes <= max_total_bytes
      - no entry name may be absolute or contain ".." segments

    Any violation raises AxonSecurityError before the entry is read into memory.
    """
    archive_size = os.path.getsize(path)
    if archive_size > max_archive_bytes:
        raise AxonSecurityError(
            f"archive exceeds max_archive_bytes ({archive_size} > {max_archive_bytes})"
        )

    with zipfile.ZipFile(path, "r") as zf:
        # Pre-flight every entry against the limits before we trust any of them.
        total_uncompressed = 0
        for info in zf.infolist():
            _safe_arcname(info.filename)
            if info.file_size > max_member_bytes:
                raise AxonSecurityError(
                    f"member {info.filename!r} uncompressed size {info.file_size} "
                    f"exceeds max_member_bytes {max_member_bytes}"
                )
            if info.compress_size > 0:
                ratio = info.file_size / max(1, info.compress_size)
                if ratio > max_compression_ratio:
                    raise AxonSecurityError(
                        f"member {info.filename!r} compression ratio {ratio:.1f} "
                        f"exceeds max_compression_ratio {max_compression_ratio} "
                        f"(possible ZIP bomb)"
                    )
            total_uncompressed += info.file_size
        if total_uncompressed > max_total_bytes:
            raise AxonSecurityError(
                f"total uncompressed size {total_uncompressed} "
                f"exceeds max_total_bytes {max_total_bytes}"
            )

        names = set(zf.namelist())

        def read_text(arcname: str) -> str:
            return zf.read(arcname).decode("utf-8")

        def read_json(arcname: str) -> Any:
            return json.loads(zf.read(arcname))

        manifest_dict = read_json("manifest.json")
        manifest = _dict_to_manifest(manifest_dict)

        content_axc = read_text("content/document.axc")
        content = parse_axc(content_axc)

        render_axr = read_text("render/default.axr")
        render = parse_axr(render_axr)
        if not render.rules:
            render = default_render_profile()

        metadata = (
            read_json("metadata/core.json") if "metadata/core.json" in names else {}
        )

        signatures = []
        if "signatures/integrity.sig" in names:
            signatures = read_json("signatures/integrity.sig")

        annotations = []
        for name in names:
            if name.startswith("annotations/") and name.endswith(".json"):
                annotations.append(read_json(name))

        deltas = []
        for name in sorted(names):
            if name.startswith("history/") and name.endswith(".axd"):
                deltas.append(read_json(name))

        queries = {}
        for name in names:
            if name.startswith("queries/") and name.endswith(".aql"):
                qname = pathlib.Path(name).stem
                queries[qname] = read_text(name)

    doc = AxonDocument(
        manifest=manifest,
        content=content,
        render=render,
        metadata=metadata,
        deltas=deltas,
        annotations=annotations,
        signatures=signatures,
        queries=queries,
    )

    if verify:
        if not verify_document(doc, content_axc, render_axr):
            raise ValueError(
                "AXON integrity violation: content or render hash mismatch. "
                "Document may be corrupted or tampered."
            )

    return doc


def _dict_to_manifest(d: dict) -> Manifest:
    m = Manifest()
    for k, v in d.items():
        if hasattr(m, k):
            setattr(m, k, v)
    return m


# ─────────────────────────────────────────────────────────────
# SECTION 10 — VALIDATION ENGINE
# ─────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [f"Valid: {self.valid}"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate(doc: AxonDocument) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    m = doc.manifest

    # Manifest checks
    if not m.title:
        errors.append("manifest.title is empty")
    if not m.document_id:
        errors.append("manifest.document_id is missing")
    if m.document_type not in DOCUMENT_TYPES:
        warnings.append(
            f"manifest.document_type '{m.document_type}' not in core registry"
        )
    if m.axon_version != AXON_VERSION:
        warnings.append(
            f"axon_version '{m.axon_version}' differs from this implementation ({AXON_VERSION})"
        )

    # Content checks
    root = doc.content
    if root.type != "document":
        errors.append(f"Content root must be @document, found @{root.type}")

    # Required sections by document type
    required = REQUIRED_SECTIONS_BY_TYPE.get(m.document_type, set())
    if required:
        section_ids = {s.attributes.get("id", "").lower() for s in root.find("section")}
        section_headings = set()
        for h in root.find("heading"):
            tc = h.text_content().lower()
            for word in tc.split():
                section_headings.add(word)
        found = section_ids | section_headings
        for req in required:
            if req not in found:
                warnings.append(
                    f"Expected section '{req}' not found for document type '{m.document_type}'"
                )

    # Image alt text
    images = root.find("image")
    for img in images:
        has_alt = (
            img.attributes.get("alt")
            or img.find_one("alt")
            or img.attributes.get("role") == "decorative"
        )
        if not has_alt:
            warnings.append(
                f"@image node missing alt text (id={img.attributes.get('id', 'unknown')})"
            )

    # Table structure
    for table in root.find("table"):
        if not table.attributes.get("summary"):
            warnings.append(
                f"@table missing summary attribute (id={table.attributes.get('id', 'unknown')})"
            )

    # Equation description
    for eq in root.find("equation"):
        if not eq.find_one("description"):
            warnings.append(
                f"@equation missing @description child "
                f"(id={eq.attributes.get('id', 'unknown')})"
            )

    # ─── AXON v1.1 — semantic-block validation ─────────────────
    # Each new node type has soft requirements: missing attributes
    # become warnings, never errors, so the document still validates
    # while the author is alerted to fill in the metadata that makes
    # the node useful for AI extraction.

    for fnd in root.find("finding"):
        fid = fnd.attributes.get("id", "unknown")
        if not fnd.attributes.get("type"):
            warnings.append(
                f"@finding missing type= (id={fid}) — use 'primary' / 'secondary' / 'exploratory'"
            )
        if not fnd.attributes.get("significance"):
            warnings.append(
                f"@finding missing significance= (id={fid}) — typically a p-value"
            )

    for hyp in root.find("hypothesis"):
        if not hyp.attributes.get("id"):
            warnings.append(
                "@hypothesis missing id= — required so @link nodes can reference it"
            )
        status = hyp.attributes.get("status", "proposed")
        if status not in ("proposed", "supported", "rejected", "inconclusive"):
            warnings.append(
                f"@hypothesis status='{status}' is non-standard "
                f"(use proposed / supported / rejected / inconclusive)"
            )

    for res in root.find("result"):
        if not res.attributes.get("metric"):
            warnings.append(
                f"@result missing metric= (id={res.attributes.get('id', 'unknown')}) "
                f"— required so AI extraction knows what is being measured"
            )

    for met in root.find("metric"):
        if not met.attributes.get("name"):
            warnings.append("@metric missing name= attribute")
        if not met.attributes.get("value") and not met.text:
            warnings.append(
                f"@metric '{met.attributes.get('name', 'unknown')}' has no value="
            )

    for nar in root.find("narrative"):
        if not nar.attributes.get("role"):
            warnings.append(
                "@narrative missing role= "
                "(use motivation / mechanism_explanation / clinical_implication / limitation / future_work)"
            )

    for cr in root.find("code_ref"):
        if not cr.attributes.get("repo"):
            warnings.append(
                "@code_ref missing repo= attribute (a public URL or owner/name)"
            )

    for lk in root.find("link"):
        if not lk.attributes.get("from") or not lk.attributes.get("to"):
            warnings.append("@link missing from= or to= attribute")
        if not lk.attributes.get("type"):
            warnings.append(
                "@link missing type= "
                "(use validated_by / derived_from / refutes / supports / contradicts / cites)"
            )

    for vw in root.find("view"):
        vt = vw.attributes.get("type", "")
        if vt not in ("linear", "graph", "summary", "outline", "data"):
            warnings.append(
                f"@view type='{vt}' is non-standard "
                f"(use linear / graph / summary / outline / data)"
            )

    # Duplicate IDs — only flag real, meaningful IDs.
    # A node without a declared id, or with an empty/placeholder id ("", "-", "—"),
    # is treated as having no id. This matches HTML semantics where an empty id
    # attribute does not participate in the document's id-name space.
    all_ids: List[str] = []
    _PLACEHOLDER_IDS = {"", "-", "—", "–"}

    def collect_ids(node: Node) -> None:
        nid = node.attributes.get("id", "").strip()
        if nid and nid not in _PLACEHOLDER_IDS:
            all_ids.append(nid)
        for child in node.children:
            collect_ids(child)

    collect_ids(root)
    seen: set = set()
    for node_id in all_ids:
        if node_id in seen:
            errors.append(f"Duplicate node id: '{node_id}'")
        seen.add(node_id)

    # Hash integrity check — both content and render hashes.
    content_axc = serialize_axc(doc.content)
    if m.content_hash:
        if hash_text(content_axc) != m.content_hash:
            errors.append(
                "Content hash mismatch — document may be modified since encoding"
            )
    if m.render_hash:
        render_axr = serialize_axr(doc.render)
        if hash_text(render_axr) != m.render_hash:
            errors.append(
                "Render hash mismatch — render profile may be modified since encoding"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ─────────────────────────────────────────────────────────────
# SECTION 11 — HTML RENDERER
# ─────────────────────────────────────────────────────────────

_HTML_ESCAPE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def _he(text: str) -> str:
    return text.translate(_HTML_ESCAPE)


class HtmlRenderer:
    def __init__(self, profile: Optional[RenderProfile] = None):
        self.profile = profile or default_render_profile()
        self._footnote_counter = 0
        self._footnotes: Dict[str, str] = {}

    def render(self, doc: AxonDocument) -> str:
        head = self._html_head(doc.manifest)
        body = self._render_node(doc.content)
        footnotes = self._render_footnote_section()
        return f'<!DOCTYPE html>\n<html lang="{_he(doc.manifest.language)}">\n{head}\n<body>\n{body}\n{footnotes}\n</body>\n</html>'

    def _html_head(self, manifest: Manifest) -> str:
        styles = self._generate_styles()
        return (
            f"<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{_he(manifest.title)}</title>\n"
            f'<meta name="description" content="AXON document: {_he(manifest.document_type)}">\n'
            f"<style>\n{styles}\n</style>\n"
            f"</head>"
        )

    def _generate_styles(self) -> str:
        # Journal-grade typography. Self-contained — no external font fetches,
        # so this works inside a sandbox="" iframe (where the Preview tab on
        # /try and /view embeds it). System-serif stack picks the best
        # available face per OS: Iowan Old Style on macOS, Cambria on Windows,
        # Liberation/DejaVu Serif on Linux.
        #
        # Includes a complete @media print block so the browser's "Save as
        # PDF" produces journal-quality output without a server-side renderer.
        return textwrap.dedent("""
            :root{
              --paper:#fdfdfb; --ink:#0e0e0c; --ink-2:#3b3a36; --ink-3:#6b6862;
              --rule:#d9d4c7; --rule-soft:#ece7d8; --accent:#7a0c1a;
              --serif:"Iowan Old Style","Sitka Text",Charter,Cambria,"Hoefler Text",Constantia,"Linux Libertine","Liberation Serif","Bitstream Charter","Times New Roman",serif;
              --mono:"SF Mono","JetBrains Mono",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
            }
            *,*::before,*::after{ box-sizing:border-box; }
            html{ background:var(--paper); }
            body{
              font-family:var(--serif);
              max-width:38rem; margin:3rem auto 5rem; padding:0 1.5rem;
              line-height:1.55; color:var(--ink); background:var(--paper);
              font-feature-settings:"onum","kern","liga"; hyphens:auto;
              -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
            }

            /* Type scale */
            h1{ font-size:2.05rem; font-weight:600; line-height:1.15; letter-spacing:-0.01em; margin:0 0 1.2rem; }
            h2{ font-size:1.35rem; font-weight:600; line-height:1.25; margin:2.4rem 0 0.6rem;
                padding-bottom:0.25rem; border-bottom:1px solid var(--rule-soft); }
            h3{ font-size:1.10rem; font-weight:600; margin:1.8rem 0 0.4rem; }
            h4,h5,h6{ font-size:1rem; font-weight:600; margin:1.4rem 0 0.3rem; color:var(--ink-2); }
            p{ margin:0 0 0.9rem; orphans:3; widows:3; }
            p + p{ text-indent:0; } /* could enable indent for academic look — leave flat */
            em,i{ font-style:italic; }
            strong,b{ font-weight:600; }
            small{ font-size:0.85em; color:var(--ink-2); }

            section{ margin:0 0 1.4rem; }
            section[id]{ scroll-margin-top:2rem; }

            /* Lists */
            ul,ol{ padding-left:1.4rem; margin:0 0 1rem; }
            li{ margin:0.15rem 0; }

            /* Tables — clean rules, no heavy box */
            table{ border-collapse:collapse; width:100%; margin:1.6rem 0;
                    font-feature-settings:"tnum","kern"; font-variant-numeric:tabular-nums; }
            caption{ caption-side:top; text-align:left; font-style:italic; color:var(--ink-2);
                     font-size:0.9rem; padding:0 0 0.4rem; }
            thead th{ border-top:1.5px solid var(--ink); border-bottom:0.8px solid var(--ink); }
            tbody tr:last-child td{ border-bottom:1.5px solid var(--ink); }
            th,td{ padding:0.45rem 0.7rem; text-align:left; vertical-align:top;
                    border-bottom:0.4px solid var(--rule); }
            th{ font-weight:600; }
            td[data-type], cell[data-type]{ font-variant-numeric:tabular-nums; }

            /* Typed cells — the AXON differentiator. Subtle underline + tooltip. */
            [data-type]{
              background-image:linear-gradient(transparent 60%, var(--accent) 60%, var(--accent) 62%, transparent 62%);
              cursor:help;
            }
            [data-type]:hover{
              background-image:linear-gradient(transparent 50%, var(--accent) 50%, var(--accent) 100%);
              color:var(--paper);
            }
            [data-type]::after{
              content:" · " attr(data-type); color:var(--ink-3);
              font-family:var(--mono); font-size:0.72em; letter-spacing:0.04em;
              text-transform:uppercase; vertical-align:0.1em;
            }
            /* Hide the type label on hover-over for a cleaner read; visible on all
               other interactions. Toggle this to "always show" if preferred. */

            /* Figures + captions */
            figure{ margin:1.8rem 0; }
            figure img,figure svg{ max-width:100%; height:auto; display:block; }
            figcaption{ font-size:0.88rem; color:var(--ink-2); margin-top:0.5rem;
                         text-align:left; font-style:italic; }
            figure[data-figure-id]::before{
              content:"Figure " attr(data-figure-id) ". ";
              font-style:normal; font-weight:600; color:var(--ink);
            }

            /* Equations — centered display, italic Latin (math mode look) */
            .equation, math, .math-display{
              display:block; text-align:center; margin:1.8rem 0;
              font-family:"Latin Modern Math",Cambria Math,"STIX Two Math",STIXGeneral,serif;
              font-size:1.05em;
            }
            .math-inline{ font-family:"Latin Modern Math",Cambria Math,STIXGeneral,serif; }

            /* Code */
            pre,code,kbd,samp{ font-family:var(--mono); font-size:0.9em; }
            pre{ background:var(--rule-soft); border-left:3px solid var(--rule);
                  padding:0.9rem 1.1rem; overflow-x:auto; margin:1.2rem 0; line-height:1.45; }
            code{ background:var(--rule-soft); padding:0.05em 0.32em; border-radius:2px; }
            pre code{ background:transparent; padding:0; }

            /* Quotes + asides + callouts — all use rules, never boxes */
            blockquote{ border-left:3px solid var(--rule); margin:1.2rem 0;
                         padding:0.2rem 0 0.2rem 1.2rem; color:var(--ink-2); font-style:italic; }
            .aside{ border-left:3px solid var(--rule); padding:0.2rem 0 0.2rem 1.2rem;
                     font-size:0.92rem; color:var(--ink-2); margin:1rem 0; }
            .callout{ border:1px solid var(--rule); padding:0.9rem 1.1rem;
                       margin:1.2rem 0; background:var(--rule-soft); }
            .callout.critical{ border-color:var(--accent); border-left-width:3px;
                                background:transparent; }
            .callout.critical::before{ content:"⚠ "; color:var(--accent); font-weight:700; }

            /* Footnotes — proper academic treatment */
            sup.footnote-ref{ font-size:0.72em; vertical-align:0.5em;
                              text-decoration:none; color:var(--accent); }
            sup.footnote-ref a{ color:inherit; }
            .footnotes{ border-top:1px solid var(--rule); margin-top:3rem;
                         padding-top:1.2rem; font-size:0.88rem; color:var(--ink-2); }
            .footnotes h2{ font-size:0.85rem; font-weight:600; text-transform:uppercase;
                            letter-spacing:0.08em; border:0; padding:0; margin:0 0 0.6rem;
                            color:var(--ink-3); }
            .footnotes ol{ padding-left:1.6rem; }

            /* Conflict markers — yellow rule on the left, never a fill */
            .axon-conflict{ border-left:3px solid #c89800; padding:0.4rem 0.9rem;
                             color:var(--ink-2); margin:0.6rem 0; }

            /* ─── AXON v1.1 — semantic research blocks ─── */
            /* All v1.1 blocks share the same visual idiom: a left-rule
               accent in oxblood, a small mono badge identifying the role,
               clean academic typography in the body. No boxes, no shadows. */

            .finding, .hypothesis, .narrative, .result{
              margin:1.4rem 0; padding:0.4rem 0 0.4rem 1.2rem;
              border-left:3px solid var(--rule);
            }
            .finding--primary{ border-left-color:var(--accent); }
            .finding__badge, .hypothesis__badge, .narrative__role, .result__metric{
              display:block; font-family:var(--mono); font-size:0.72rem;
              letter-spacing:0.08em; text-transform:uppercase;
              color:var(--ink-3); margin:0 0 0.4rem;
            }
            .finding--primary .finding__badge{ color:var(--accent); }
            .finding__body, .hypothesis__body{ color:var(--ink); }
            .hypothesis--rejected .hypothesis__badge{ color:#a35; }
            .hypothesis--supported .hypothesis__badge{ color:#2a6; }

            .narrative__role{ display:inline-block; margin-right:0.6rem;
                              padding:0.05em 0.4em; border:1px solid var(--rule); }
            .narrative--motivation, .narrative--clinical_implication{ border-left-color:var(--accent); }

            .result__values{ display:grid; grid-template-columns:auto 1fr;
                             gap:0.2rem 1rem; margin:0.4rem 0;
                             font-family:var(--mono); font-size:0.86rem;
                             font-variant-numeric:tabular-nums; }
            .result__values dt{ color:var(--ink-3); }
            .result__values dd{ margin:0; color:var(--ink); }

            .metric{ font-variant-numeric:tabular-nums; font-feature-settings:"tnum"; }
            .metric__value{ font-weight:600; }
            .metric__unit{ color:var(--ink-3); font-size:0.92em; }

            .code-ref{ font-family:var(--mono); font-size:0.86rem;
                       margin:0.6rem 0; padding:0.4rem 0.7rem;
                       background:var(--rule-soft); }
            .code-ref__label{ color:var(--ink-3); text-transform:uppercase;
                              letter-spacing:0.08em; font-size:0.74rem; margin-right:0.4em; }
            .code-ref a{ color:var(--accent); text-decoration:underline; }

            .axon-link{ font-family:var(--mono); font-size:0.78rem;
                        color:var(--ink-3); margin:0.4rem 0; }
            .axon-link__rel{ font-style:italic; color:var(--accent); }

            /* @view declarations are metadata, hidden in human render */
            .axon-view{ display:none; }

            /* Inline links */
            a{ color:var(--ink); text-decoration-thickness:1px;
                text-underline-offset:3px; text-decoration-color:var(--rule); }
            a:hover{ color:var(--accent); text-decoration-color:var(--accent); }

            /* Selection */
            ::selection{ background:var(--accent); color:var(--paper); }

            /* ─── PRINT — journal-quality "Save as PDF" output ─── */
            @media print{
              @page{ size:A4; margin:22mm 18mm; }
              @page :first{ margin-top:30mm; }
              html,body{ background:white; }
              body{ max-width:none; margin:0; padding:0; font-size:10.5pt; line-height:1.45; }
              h1{ font-size:18pt; }
              h2{ font-size:13pt; page-break-after:avoid; }
              h3{ font-size:11pt; page-break-after:avoid; }
              h1,h2,h3,h4{ page-break-after:avoid; }
              p,li,table,figure,blockquote,pre{ page-break-inside:avoid; }
              table{ font-size:9.5pt; }
              pre{ font-size:8.5pt; white-space:pre-wrap; word-wrap:break-word; }
              a{ color:var(--ink); text-decoration:none; }
              /* Show type annotations as small text in print, not as underlines */
              [data-type]{ background:none; }
              [data-type]::after{ font-size:0.65em; }
              /* Hide footnotes' header — kept the list */
              .footnotes h2{ display:none; }
            }
        """).strip()

    def _render_node(self, node: Node) -> str:
        t = node.type
        if t == "document":
            return "\n".join(self._render_node(c) for c in node.children)
        if t == "section":
            inner = "\n".join(self._render_node(c) for c in node.children)
            sid = node.attributes.get("id", "")
            return f'<section id="{_he(sid)}">\n{inner}\n</section>'
        if t == "heading":
            level = int(node.attributes.get("level", "2"))
            level = max(1, min(6, level))
            text = _he(node.text_content())
            return f"<h{level}>{text}</h{level}>"
        if t == "paragraph":
            inner = self._render_inline(node.text)
            for child in node.children:
                inner += self._render_node(child)
            return f"<p>{inner}</p>"
        if t in ("list",):
            ordered = node.attributes.get("ordered", "false") == "true"
            tag = "ol" if ordered else "ul"
            inner = "\n".join(self._render_node(c) for c in node.children)
            return f"<{tag}>\n{inner}\n</{tag}>"
        if t == "item":
            inner = self._render_inline(node.text)
            for child in node.children:
                inner += self._render_node(child)
            return f"<li>{inner}</li>"
        if t == "table":
            summary = _he(node.attributes.get("summary", ""))
            caption_node = node.find_one("caption")
            caption = (
                f"<caption>{_he(caption_node.text_content())}</caption>\n"
                if caption_node
                else ""
            )
            rows = "\n".join(
                self._render_node(c)
                for c in node.children
                if c.type in ("thead", "tbody")
            )
            return f'<table aria-label="{summary}">\n{caption}{rows}\n</table>'
        if t == "thead":
            rows = "\n".join(self._render_node(c) for c in node.children)
            return f"<thead>\n{rows}\n</thead>"
        if t == "tbody":
            rows = "\n".join(self._render_node(c) for c in node.children)
            return f"<tbody>\n{rows}\n</tbody>"
        if t == "row":
            cells = "\n".join(self._render_node(c) for c in node.children)
            return f"<tr>\n{cells}\n</tr>"
        if t == "cell":
            scope = node.attributes.get("scope", "")
            dt = node.attributes.get("data-type", "")
            dv = node.attributes.get("data-value", node.text)
            tag = "th" if scope else "td"
            attrs = f' scope="{_he(scope)}"' if scope else ""
            if dt:
                attrs += f' data-type="{_he(dt)}"'
            if dv:
                attrs += f' data-value="{_he(dv)}"'
            css = f' class="data-{_he(dt)}"' if dt else ""
            inner = self._render_inline(node.text)
            return f"<{tag}{attrs}{css}>{inner}</{tag}>"
        if t == "figure":
            inner = "\n".join(
                self._render_node(c) for c in node.children if c.type != "caption"
            )
            cap = node.find_one("caption")
            caption = (
                f"<figcaption>{_he(cap.text_content())}</figcaption>" if cap else ""
            )
            fid = node.attributes.get("id", "")
            return f'<figure id="{_he(fid)}">\n{inner}\n{caption}\n</figure>'
        if t == "image":
            src = node.attributes.get("src", "")
            alt = node.attributes.get("alt", node.text_content())
            role = node.attributes.get("role", "")
            if role == "decorative":
                return f'<img src="{_he(src)}" alt="" aria-hidden="true">'
            return f'<img src="{_he(src)}" alt="{_he(alt)}">'
        if t == "equation":
            eq_id = node.attributes.get("id", "")
            label = node.attributes.get("label", "")
            latex_node = node.find_one("latex")
            desc_node = node.find_one("description")
            latex = latex_node.text_content() if latex_node else node.text
            desc = desc_node.text_content() if desc_node else ""
            return (
                f'<div class="equation" id="{_he(eq_id)}" '
                f'aria-label="{_he(desc)}">\n'
                f"  <code>{_he(latex)}</code>\n"
                f'  <span class="equation-label">{_he(label)}</span>\n'
                f"</div>"
            )
        if t == "code":
            lang = node.attributes.get("lang", "")
            inner = _he(node.text_content())
            return f'<pre><code class="language-{_he(lang)}">{inner}</code></pre>'
        if t == "blockquote":
            inner = self._render_inline(node.text)
            return f"<blockquote>{inner}</blockquote>"
        if t == "callout":
            severity = node.attributes.get("severity", "")
            inner = self._render_inline(node.text)
            return f'<div class="callout {_he(severity)}">{inner}</div>'
        if t == "aside":
            inner = self._render_inline(node.text)
            return f'<aside class="aside">{inner}</aside>'
        if t == "footnote":
            fid = node.attributes.get("id", "")
            self._footnotes[fid] = node.text_content()
            return ""
        if t == "conflict":
            inner = self._render_inline(node.text)
            return f'<div class="axon-conflict" role="alert">⚠ Unresolved conflict: {inner}</div>'

        # ─── AXON v1.1 — semantic research-document node types ───
        # See `AXON v1.1` section of the spec; each renders to a
        # semantically-labelled HTML block so AI tools can extract
        # structure without rendering, and humans see a clean visual.

        if t == "finding":
            kind = node.attributes.get("type", "")
            sig = node.attributes.get("significance", "")
            valid = node.attributes.get("validated", "")
            badge_bits = [
                b
                for b in [kind, sig and f"p = {sig}", valid and f"validated · {valid}"]
                if b
            ]
            badge = " · ".join(badge_bits)
            inner = self._render_inline(node.text)
            child_html = "\n".join(self._render_node(c) for c in node.children)
            return (
                f'<aside class="finding finding--{_he(kind) or "secondary"}" '
                f'data-finding-type="{_he(kind)}" data-significance="{_he(sig)}" data-validated="{_he(valid)}">\n'
                f'  <header class="finding__badge">Finding{" · " + _he(badge) if badge else ""}</header>\n'
                f'  <div class="finding__body">{inner}{child_html}</div>\n'
                f"</aside>"
            )

        if t == "hypothesis":
            hid = node.attributes.get("id", "")
            status = node.attributes.get("status", "proposed")
            inner = self._render_inline(node.text)
            child_html = "\n".join(self._render_node(c) for c in node.children)
            return (
                f'<aside class="hypothesis hypothesis--{_he(status)}" '
                f'id="{_he(hid)}" data-hypothesis-id="{_he(hid)}" data-hypothesis-status="{_he(status)}">\n'
                f'  <header class="hypothesis__badge">H{": " + _he(hid) if hid else ""} · {_he(status)}</header>\n'
                f'  <div class="hypothesis__body">{inner}{child_html}</div>\n'
                f"</aside>"
            )

        if t == "result":
            metric = node.attributes.get("metric", "")
            method = node.attributes.get("method", "")
            # Every attribute except metric/method/id is treated as a numeric
            # group/value the result encodes — render as a small definition list
            # for humans, keep the data-* attrs for AI extraction.
            data_attrs = " ".join(
                f'data-{_he(k)}="{_he(v)}"'
                for k, v in sorted(node.attributes.items())
                if k not in ("metric", "method", "id")
            )
            id_attr = (
                f' id="{_he(node.attributes.get("id", ""))}"'
                if node.attributes.get("id")
                else ""
            )
            rows = []
            for k, v in sorted(node.attributes.items()):
                if k in ("metric", "method", "id"):
                    continue
                rows.append(f'<dt>{_he(k)}</dt><dd data-type="numeric">{_he(v)}</dd>')
            inner = self._render_inline(node.text)
            child_html = "\n".join(self._render_node(c) for c in node.children)
            return (
                f'<section class="result"{id_attr} data-metric="{_he(metric)}" data-method="{_he(method)}" {data_attrs}>\n'
                f'  <header class="result__metric">{_he(metric or "result")}'
                f'{(" · " + _he(method)) if method else ""}</header>\n'
                f'  <dl class="result__values">\n    '
                + "\n    ".join(rows)
                + "\n  </dl>\n"
                f"  {inner}{child_html}\n"
                f"</section>"
            )

        if t == "metric":
            name = node.attributes.get("name", "")
            value = node.attributes.get("value", node.text or "")
            unit = node.attributes.get("unit", "")
            group = node.attributes.get("group", "")
            return (
                f'<span class="metric" data-metric-name="{_he(name)}" '
                f'data-metric-value="{_he(value)}" data-metric-unit="{_he(unit)}" '
                f'data-metric-group="{_he(group)}">'
                f'<span class="metric__value">{_he(value)}</span>'
                f'<span class="metric__unit">{(" " + _he(unit)) if unit else ""}</span>'
                f"</span>"
            )

        if t == "narrative":
            role = node.attributes.get("role", "general")
            inner = self._render_inline(node.text)
            child_html = "\n".join(self._render_node(c) for c in node.children)
            return (
                f'<section class="narrative narrative--{_he(role)}" data-narrative-role="{_he(role)}">\n'
                f'  <span class="narrative__role">{_he(role.replace("_", " "))}</span>\n'
                f"  {inner}{child_html}\n"
                f"</section>"
            )

        if t == "code_ref":
            repo = node.attributes.get("repo", "")
            script = node.attributes.get("script", "")
            commit = node.attributes.get("commit", "")
            repro = node.attributes.get("reproducible", "")
            href_bits = []
            if repo:
                href_bits.append(repo)
            if commit:
                href_bits.append("commit/" + commit)
            elif script:
                href_bits.append("blob/main/" + script)
            url = "/".join(b.rstrip("/") for b in href_bits) if href_bits else ""
            url_attr = (
                f'href="https://{_he(url)}"'
                if url and not url.startswith(("http://", "https://"))
                else f'href="{_he(url)}"'
                if url
                else ""
            )
            link_text = (
                " / ".join(b for b in [repo, script, commit] if b) or "(unspecified)"
            )
            badge = (
                " · reproducible"
                if repro and repro.lower() not in ("false", "0", "no")
                else ""
            )
            return (
                f'<div class="code-ref" data-repo="{_he(repo)}" data-script="{_he(script)}" '
                f'data-commit="{_he(commit)}" data-reproducible="{_he(repro)}">\n'
                f'  <span class="code-ref__label">code</span> '
                f'<a {url_attr} rel="noopener">{_he(link_text)}</a>{badge}\n'
                f"</div>"
            )

        if t == "link":
            src = node.attributes.get("from", "")
            dst = node.attributes.get("to", "")
            kind = node.attributes.get("type", "related")
            label_map = {
                "validated_by": "validated by",
                "derived_from": "derived from",
                "refutes": "refutes",
                "supports": "supports",
                "contradicts": "contradicts",
                "implements": "implements",
                "cites": "cites",
                "related": "related to",
            }
            label = label_map.get(kind, kind.replace("_", " "))
            return (
                f'<div class="axon-link" '
                f'data-link-from="{_he(src)}" data-link-to="{_he(dst)}" data-link-type="{_he(kind)}">\n'
                f'  <a href="#{_he(src)}">{_he(src) or "?"}</a>'
                f' <span class="axon-link__rel">{_he(label)}</span> '
                f'<a href="#{_he(dst)}">{_he(dst) or "?"}</a>\n'
                f"</div>"
            )

        if t == "view":
            # @view declarations are document-level metadata (which views
            # this document supports). Recorded as a hidden meta block —
            # AI tools / future viewers read the data-view-type attribute.
            view_type = node.attributes.get("type", "linear")
            return (
                f'<meta class="axon-view" '
                f'data-view-type="{_he(view_type)}" '
                f'aria-hidden="true">'
            )

        if t in ("latex", "description", "notation_definitions", "caption"):
            return ""  # Rendered as part of parent
        if t == "data":
            return f'<!-- @data id={node.attributes.get("id", "")} -->'
        # Generic fallback: render children
        return "\n".join(self._render_node(c) for c in node.children)

    def _render_inline(self, text: str) -> str:
        if not text:
            return ""
        parts = parse_inline(text)
        out = []
        for part in parts:
            if isinstance(part, str):
                out.append(_he(part))
            elif isinstance(part, InlineSpan):
                out.append(self._render_span(part))
        return "".join(out)

    def _render_span(self, span: InlineSpan) -> str:
        t = span.type
        c = _he(span.content)
        if t == "em":
            return f"<em>{c}</em>"
        if t == "strong":
            return f"<strong>{c}</strong>"
        if t == "cite":
            ref = _he(span.attributes.get("ref", ""))
            return f'<cite><a href="#{ref}">{c}</a></cite>'
        if t == "link":
            href = _he(span.attributes.get("href", "#"))
            return f'<a href="{href}">{c}</a>'
        if t == "abbr":
            title = _he(span.attributes.get("title", ""))
            return f'<abbr title="{title}">{c}</abbr>'
        if t == "math":
            return f'<span class="inline-math"><code>{c}</code></span>'
        if t == "code":
            return f"<code>{c}</code>"
        if t == "mark":
            css = _he(span.attributes.get("class", ""))
            return f'<mark class="{css}">{c}</mark>'
        if t == "note":
            ref_id = span.attributes.get("ref", "")
            self._footnote_counter += 1
            n = self._footnote_counter
            return f'<sup class="footnote-ref"><a href="#fn-{_he(ref_id)}" id="fnref-{n}">[{n}]</a></sup>'
        if t == "time":
            dt = _he(span.attributes.get("datetime", ""))
            return f'<time datetime="{dt}">{c}</time>'
        if t == "lang":
            lang = _he(span.attributes.get("lang", ""))
            return f'<span lang="{lang}">{c}</span>'
        return f"<span>{c}</span>"

    def _render_footnote_section(self) -> str:
        if not self._footnotes:
            return ""
        items = []
        for fid, content in self._footnotes.items():
            items.append(f'<li id="fn-{_he(fid)}">{_he(content)}</li>')
        return (
            '<section class="footnotes">\n<h2>Notes</h2>\n<ol>\n'
            + "\n".join(items)
            + "\n</ol>\n</section>"
        )


def render_html(doc: AxonDocument) -> str:
    return HtmlRenderer(doc.render).render(doc)


# ─────────────────────────────────────────────────────────────
# SECTION 12 — PLAIN-TEXT RENDERER
# ─────────────────────────────────────────────────────────────


class PlainTextRenderer:
    def __init__(self, width: int = 80):
        self.width = width

    def render(self, doc: AxonDocument) -> str:
        lines: List[str] = []
        self._render_node(doc.content, lines, depth=0)
        return "\n".join(lines)

    def _render_node(self, node: Node, lines: List[str], depth: int) -> None:
        t = node.type
        if t == "document":
            for c in node.children:
                self._render_node(c, lines, depth)
        elif t == "section":
            lines.append("")
            for c in node.children:
                self._render_node(c, lines, depth + 1)
        elif t == "heading":
            level = int(node.attributes.get("level", "2"))
            text = node.text_content()
            marker = "#" * level
            lines.append("")
            lines.append(f"{marker} {text}")
            lines.append("")
        elif t == "paragraph":
            text = node.text_content()
            wrapped = textwrap.fill(text, width=self.width)
            lines.append(wrapped)
            lines.append("")
        elif t == "list":
            for i, c in enumerate(node.children):
                ordered = node.attributes.get("ordered", "false") == "true"
                prefix = f"{i+1}." if ordered else "-"
                text = c.text_content()
                lines.append(f"  {prefix} {text}")
            lines.append("")
        elif t == "table":
            self._render_table(node, lines)
        elif t == "figure":
            cap = node.find_one("caption")
            if cap:
                lines.append(f"[Figure: {cap.text_content()}]")
            else:
                lines.append("[Figure]")
            lines.append("")
        elif t == "equation":
            latex = node.find_one("latex")
            label = node.attributes.get("label", "")
            eq_text = latex.text_content() if latex else node.text
            lines.append(f"  [{label}]  {eq_text}")
            lines.append("")
        elif t == "code":
            lines.append("```")
            lines.append(node.text_content())
            lines.append("```")
            lines.append("")
        elif t == "blockquote":
            text = textwrap.fill(node.text_content(), width=self.width - 2)
            for line in text.splitlines():
                lines.append(f"  > {line}")
            lines.append("")
        elif t == "callout":
            text = textwrap.fill(node.text_content(), width=self.width - 6)
            severity = node.attributes.get("severity", "info").upper()
            lines.append(f"[{severity}] {text}")
            lines.append("")
        elif t in (
            "caption",
            "latex",
            "description",
            "notation_definitions",
            "footnote",
            "data",
            "signatures",
        ):
            pass
        else:
            for c in node.children:
                self._render_node(c, lines, depth)

    def _render_table(self, node: Node, lines: List[str]) -> None:
        all_rows: List[List[str]] = []
        for child in node.children:
            if child.type in ("thead", "tbody"):
                for row in child.children:
                    if row.type == "row":
                        row_data = [
                            c.text_content() for c in row.children if c.type == "cell"
                        ]
                        all_rows.append(row_data)
        if not all_rows:
            return
        cols = max(len(r) for r in all_rows) if all_rows else 0
        widths = [0] * cols
        for row in all_rows:
            for j, cell in enumerate(row):
                if j < cols:
                    widths[j] = max(widths[j], len(cell))
        sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        lines.append(sep)
        for i, row in enumerate(all_rows):
            cells = []
            for j in range(cols):
                val = row[j] if j < len(row) else ""
                cells.append(f" {val.ljust(widths[j])} ")
            lines.append("|" + "|".join(cells) + "|")
            if i == 0:
                lines.append(sep)
        lines.append(sep)
        lines.append("")


def render_text(doc: AxonDocument, width: int = 80) -> str:
    return PlainTextRenderer(width=width).render(doc)


# ─────────────────────────────────────────────────────────────
# SECTION 13 — PDF CONVERTER
# ─────────────────────────────────────────────────────────────


def _try_import_fitz():
    try:
        import fitz

        return fitz
    except ImportError:
        return None


def _pdf_classify_line(text: str, bbox: list, page_width: float) -> str:
    """Heuristically classify a line as heading, body, metadata, etc."""
    t = text.strip()
    if not t:
        return "empty"
    x0 = bbox[0]
    font_size_proxy = bbox[3] - bbox[1]  # height as proxy

    if font_size_proxy > 14:
        return "heading"
    if font_size_proxy > 11 and len(t.split()) < 10:
        return "subheading"
    if x0 < 100 and len(t) < 60 and t[0].isupper():
        return "heading_candidate"
    if re.match(r"^\s*\d+\.?\s", t):
        return "list_item"
    if re.match(r"^\s*[-•*]\s", t):
        return "list_item"
    return "paragraph"


def convert_pdf(
    pdf_path: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    document_type: str = "article.research",
) -> AxonDocument:
    """Convert a PDF to an AxonDocument using geometric layout analysis."""
    fitz = _try_import_fitz()
    if fitz is None:
        raise ImportError(
            "PyMuPDF is required for PDF conversion. "
            "Install with: pip install PyMuPDF"
        )

    doc = fitz.open(pdf_path)
    manifest = Manifest(
        title=title or pathlib.Path(pdf_path).stem,
        document_type=document_type,
        native_axon=False,
        conversion_tool="axon-pdf-converter-v1.0",
    )
    if author:
        manifest.authors = [{"name": author, "role": "author"}]

    root = Node(type="document")
    current_section = Node(type="section", attributes={"id": "body"})
    root.children.append(current_section)
    current_paragraph_lines: List[str] = []
    section_counter = 0

    def flush_paragraph() -> None:
        if current_paragraph_lines:
            text = " ".join(current_paragraph_lines)
            if text.strip():
                p = Node(type="paragraph", text=text.strip())
                current_section.children.append(p)
            current_paragraph_lines.clear()

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_width = page.rect.width
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))

        for block in blocks:
            if block[6] != 0:  # skip image blocks
                continue
            block_text = block[4].strip()
            if not block_text:
                continue
            bbox = [block[0], block[1], block[2], block[3]]
            lines_in_block = [
                ln.strip() for ln in block_text.splitlines() if ln.strip()
            ]

            for line_text in lines_in_block:
                kind = _pdf_classify_line(line_text, bbox, page_width)

                if kind in ("heading", "subheading", "heading_candidate"):
                    flush_paragraph()
                    level = 2 if kind == "subheading" else 1
                    section_counter += 1
                    sid = re.sub(r"\W+", "-", line_text.lower()).strip("-")[:30]
                    if not sid:
                        sid = f"section-{section_counter}"
                    new_section = Node(type="section", attributes={"id": sid})
                    heading = Node(
                        type="heading", attributes={"level": str(level)}, text=line_text
                    )
                    new_section.children.append(heading)
                    root.children.append(new_section)
                    # Update current section reference
                    current_section.children.clear()
                    current_section = new_section

                elif kind == "list_item":
                    flush_paragraph()
                    # Find or create a list node
                    if (
                        not current_section.children
                        or current_section.children[-1].type != "list"
                    ):
                        lst = Node(type="list")
                        current_section.children.append(lst)
                    item_text = re.sub(r"^[\d\.\-•*]\s*", "", line_text)
                    item = Node(type="item", text=item_text)
                    current_section.children[-1].children.append(item)

                else:
                    current_paragraph_lines.append(line_text)

    flush_paragraph()

    render = default_render_profile()
    return AxonDocument(manifest=manifest, content=root, render=render)


# ─────────────────────────────────────────────────────────────
# SECTION 14 — JSON-SDF CONVERTER
# ─────────────────────────────────────────────────────────────


def convert_json_sdf(
    json_path: str,
    title: str = "Converted Document",
    document_type: str = "report.technical",
) -> AxonDocument:
    """Convert a JSON-SDF pipeline output (from the geometric pipeline) to AXON."""
    with open(json_path, "r", encoding="utf-8") as f:
        pages: List[dict] = json.load(f)

    manifest = Manifest(
        title=title,
        document_type=document_type,
        native_axon=False,
        conversion_tool="axon-json-sdf-converter-v1.0",
    )

    root = Node(type="document")
    section = Node(type="section", attributes={"id": "body"})
    root.children.append(section)

    current_para_lines: List[str] = []
    section_counter = 0
    current_section = section

    def flush_para() -> None:
        if current_para_lines:
            text = " ".join(current_para_lines).strip()
            if text:
                p = Node(type="paragraph", text=text)
                current_section.children.append(p)
            current_para_lines.clear()

    for page in pages:
        for line in page.get("lines", []):
            text = line.get("text", "").strip()
            if not text:
                continue

            # Use KV pairs if present
            kv_pairs = line.get("kv_pairs", [])
            bbox = line.get("bbox", [0, 0, 0, 0])
            height = bbox[3] - bbox[1] if len(bbox) >= 4 else 10

            # Classify based on height and content
            is_heading = (
                height > 12 and len(text.split()) < 12 and not text.endswith(".")
            )
            is_kv = bool(kv_pairs) and kv_pairs[0].get("confidence") == "high"

            if is_heading:
                flush_para()
                section_counter += 1
                sid = re.sub(r"\W+", "-", text.lower())[:30]
                new_sec = Node(
                    type="section", attributes={"id": sid or f"sec-{section_counter}"}
                )
                h = Node(type="heading", attributes={"level": "2"}, text=text)
                new_sec.children.append(h)
                root.children.append(new_sec)
                current_section = new_sec

            elif is_kv:
                flush_para()
                for kv in kv_pairs:
                    key = kv.get("key", "")
                    val = kv.get("value", "")
                    dt = _infer_data_type(val)
                    defn = Node(
                        type="definition",
                        attributes={
                            "data-type": dt,
                            "confidence": kv.get("confidence", "medium"),
                        },
                    )
                    defn.children.append(Node(type="paragraph", text=f"{key}: {val}"))
                    current_section.children.append(defn)

            else:
                current_para_lines.append(text)

    flush_para()

    render = default_render_profile()
    return AxonDocument(manifest=manifest, content=root, render=render)


def _infer_data_type(value: str) -> str:
    """Infer an AXON data type from a string value."""
    v = value.strip()
    if re.match(r"^-?\d+\.\d+$", v):
        f = float(v)
        if 0 <= f <= 1:
            return "ratio"
        return "number"
    if re.match(r"^-?\d+$", v):
        return "number"
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return "date"
    if re.match(r"^10\.\d{4,}/", v):
        return "identifier"
    if re.match(r"^https?://", v):
        return "identifier"
    if re.match(r"^\d+(\.\d+)?\s*%$", v):
        return "percentage"
    return "text"


def convert_axc_string(
    axc_text: str,
    title: str = "Document",
    document_type: str = "article.research",
    authors: Optional[List[dict]] = None,
) -> AxonDocument:
    """Build an AxonDocument from a raw AXC string."""
    manifest = Manifest(title=title, document_type=document_type)
    if authors:
        manifest.authors = authors
    content = parse_axc(axc_text)
    render = default_render_profile()
    return AxonDocument(manifest=manifest, content=content, render=render)


def encode_pdf_with_axon(doc: AxonDocument) -> bytes:
    """Render an AxonDocument as a PDF *with the AXON tree embedded inside*.

    This is the "PDF/A-3" pattern (the same pattern ZUGFeRD invoices use to
    embed XML and PMC papers use to embed JATS): the visual layer is a
    normal PDF that opens in every viewer; the structural layer is a set of
    file attachments inside the PDF that AI tools and AXON-aware readers
    can pull out with a single embedded-files API call.

    Embedded files (canonical names):
      axon-manifest.json     — manifest dict, JSON
      axon-content.axc       — canonical .axc serialization
      axon-render.axr        — render profile, .axr text (when present)
      axon-signature.json    — hash-integrity record (Ed25519 if cryptography is available)
      axon-spec-pointer.txt  — one-liner pointing to the AXON spec URL

    Output is a single byte-string; callers write it to disk or return it
    over HTTP. The .pdf file IS the .tdoc archive — same data, different
    container, universally compatible.
    """
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "encode_pdf_with_axon needs PyMuPDF — add 'PyMuPDF>=1.23' to requirements."
        ) from e

    # 1. Build the canonical AXON artifacts that will be embedded.
    content_axc = serialize_axc(doc.content)
    render_axr = serialize_axr(doc.render)
    content_hash, render_hash = compute_document_hashes(content_axc, render_axr)
    doc.manifest.content_hash = content_hash
    doc.manifest.render_hash = render_hash
    manifest_dict = doc.manifest.to_dict()
    signature = sign_document(content_axc, render_axr, manifest_dict)

    # 2. Render the document HTML and lay it out into PDF pages via Story.
    html = render_html(doc)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    A4 = fitz.paper_rect("A4")
    margin = 56  # ~20 mm — matches the @page margin in the print stylesheet
    where = fitz.Rect(margin, margin, A4.width - margin, A4.height - margin)
    story = fitz.Story(html=html)
    more = 1
    pages = 0
    # Cap at 200 pages — defence in depth against pathological inputs.
    while more and pages < 200:
        dev = writer.begin_page(A4)
        more, _filled = story.place(where)
        story.draw(dev, fitz.Identity)
        writer.end_page()
        pages += 1
    writer.close()

    # 3. Re-open the PDF to attach embedded files + write XMP metadata.
    pdf = fitz.open(stream=buf.getvalue(), filetype="pdf")

    pdf.set_metadata(
        {
            "title": doc.manifest.title or "Untitled",
            "author": ", ".join(
                a.get("name", "") for a in (doc.manifest.authors or []) if a.get("name")
            )
            or "",
            "subject": doc.manifest.document_type or "",
            "keywords": "AXON, tdoc, structured-document, ai-readable",
            "producer": "tdoc",
            "creator": "tdoc",
        }
    )

    def _embed(name: str, data: bytes, desc: str) -> None:
        pdf.embfile_add(name, data, ufilename=name, desc=desc)

    _embed(
        "axon-manifest.json",
        json.dumps(manifest_dict, sort_keys=True, indent=2, ensure_ascii=False).encode(
            "utf-8"
        ),
        "AXON manifest — document_id, hashes, declared types",
    )
    _embed(
        "axon-content.axc",
        content_axc.encode("utf-8"),
        "AXON content notation — the structural source of truth",
    )
    _embed(
        "axon-render.axr",
        render_axr.encode("utf-8"),
        "AXON render profile — typography + layout hints",
    )
    _embed(
        "axon-signature.json",
        json.dumps([signature], sort_keys=True, indent=2, ensure_ascii=False).encode(
            "utf-8"
        ),
        "AXON integrity record — hash of the canonical signing payload",
    )
    _embed(
        "axon-spec-pointer.txt",
        (
            "AXON format v1.0 - "
            "https://github.com/LuciferMors/tdoc/blob/main/AXON_Format_Specification.txt\n"
        ).encode("utf-8"),
        "Pointer to the AXON specification",
    )

    # 4. Save with garbage collection + deflate so the PDF stays compact.
    out = io.BytesIO()
    pdf.save(out, garbage=4, deflate=True, clean=True)
    return out.getvalue()


def parse_pdf_with_axon(pdf_bytes: bytes) -> AxonDocument:
    """Open a PDF, extract the embedded AXON files, reconstruct the document.

    Round-trip contract: encode_pdf_with_axon(doc) followed by this function
    yields a document that re-serializes to the same content_hash. PDFs
    without an axon-content.axc attachment raise AxonSecurityError (so the
    upload pipeline returns a clean 4xx, not a stack trace).
    """
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "parse_pdf_with_axon needs PyMuPDF — add 'PyMuPDF>=1.23' to requirements."
        ) from e

    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise AxonSecurityError(f"Not a valid PDF: {e}") from e

    # Locate axon-content.axc among the embedded files.
    names = {pdf.embfile_info(i)["filename"]: i for i in range(pdf.embfile_count())}
    if "axon-content.axc" not in names:
        raise AxonSecurityError(
            "PDF has no axon-content.axc embedded file — not a tdoc-flavoured PDF"
        )

    content_axc = pdf.embfile_get(names["axon-content.axc"]).decode("utf-8")
    render_axr = (
        pdf.embfile_get(names["axon-render.axr"]).decode("utf-8")
        if "axon-render.axr" in names
        else ""
    )
    manifest_dict: dict = {}
    if "axon-manifest.json" in names:
        try:
            manifest_dict = json.loads(
                pdf.embfile_get(names["axon-manifest.json"]).decode("utf-8")
            )
        except (UnicodeDecodeError, ValueError):
            manifest_dict = {}

    manifest = Manifest(
        title=manifest_dict.get("title", "Untitled"),
        document_type=manifest_dict.get("document_type", "article.research"),
    )
    for k, v in manifest_dict.items():
        if hasattr(manifest, k) and not callable(getattr(manifest, k)):
            try:
                setattr(manifest, k, v)
            except (AttributeError, TypeError):
                pass

    content = parse_axc(content_axc)
    render = parse_axr(render_axr) if render_axr else default_render_profile()
    return AxonDocument(manifest=manifest, content=content, render=render)


def parse_tdoc_archive(archive_bytes: bytes) -> AxonDocument:
    """Open a .tdoc archive (deterministic ZIP) and reconstruct the document.

    Round-trip contract: encode_archive(doc) followed by parse_tdoc_archive
    on the resulting bytes returns a document that re-serializes to the same
    .axc + manifest fields. Renders are restored when present, else the
    default render profile is used.

    Security: ZIP entries are size-checked and path-sanitised exactly as
    other AXON archive readers do. Total uncompressed size is capped to
    avoid zip-bomb attacks.
    """
    # Hard caps — same defence-in-depth posture as the rest of the codebase.
    _MAX_ENTRIES = 1024
    _MAX_UNCOMPRESSED = 64 * 1024 * 1024  # 64 MiB total after decompression

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as e:
        raise AxonSecurityError(f"Not a valid .tdoc archive: {e}") from e

    names = zf.namelist()
    if len(names) > _MAX_ENTRIES:
        raise AxonSecurityError(
            f".tdoc has {len(names)} entries; cap is {_MAX_ENTRIES}"
        )
    total = sum(i.file_size for i in zf.infolist())
    if total > _MAX_UNCOMPRESSED:
        raise AxonSecurityError(
            f".tdoc uncompressed size {total} exceeds {_MAX_UNCOMPRESSED}"
        )
    for name in names:
        # Reject path traversal / absolute paths just like the canonical reader.
        if name.startswith("/") or ".." in name.split("/"):
            raise AxonSecurityError(f"Unsafe entry path: {name!r}")

    if "manifest.json" not in names:
        raise AxonSecurityError("missing manifest.json in .tdoc archive")
    if "content/document.axc" not in names:
        raise AxonSecurityError("missing content/document.axc in .tdoc archive")

    manifest_dict = json.loads(zf.read("manifest.json").decode("utf-8"))
    axc_text = zf.read("content/document.axc").decode("utf-8")
    render_text = (
        zf.read("render/default.axr").decode("utf-8")
        if "render/default.axr" in names
        else ""
    )

    # Rehydrate manifest. Missing fields fall back to dataclass defaults.
    manifest = Manifest(
        title=manifest_dict.get("title", "Untitled"),
        document_type=manifest_dict.get("document_type", "article.research"),
    )
    for k, v in manifest_dict.items():
        if hasattr(manifest, k) and not callable(getattr(manifest, k)):
            try:
                setattr(manifest, k, v)
            except (AttributeError, TypeError):
                pass

    content = parse_axc(axc_text)
    render = parse_axr(render_text) if render_text else default_render_profile()
    return AxonDocument(manifest=manifest, content=content, render=render)


# ─────────────────────────────────────────────────────────────
# SECTION 15 — AQL QUERY ENGINE
# ─────────────────────────────────────────────────────────────

# AQL grammar (subset implemented):
#   QUERY <name>
#   FROM @<type> [<attr-filter>]
#   SELECT <field> [, <field>]*
#   [WHERE <condition>]
#   [ORDER BY <field> [ASC|DESC]]
#   [LIMIT <n>]
#   RETURNS <table|list|value>

_AQL_QUERY = re.compile(
    r"QUERY\s+(\w+)\s*"
    r"FROM\s+@(\w+)(?:\s*\[([^\]]*)\])?\s*"
    r"SELECT\s+([^\n]+)\s*"
    r"(?:WHERE\s+([^\n]+)\s*)?"
    r"(?:ORDER\s+BY\s+([\w-]+)(?:\s+(ASC|DESC))?\s*)?"
    r"(?:LIMIT\s+(\d+)\s*)?"
    r"RETURNS\s+(\w+)",
    re.IGNORECASE | re.DOTALL,
)

_AQL_CONDITION = re.compile(
    r'([\w\-]+)\s*(==|!=|<|>|<=|>=|CONTAINS|=)\s*(["\']?)([^"\'>\s]+)\3', re.IGNORECASE
)


def _eval_condition(node: Node, condition: str) -> bool:
    if not condition:
        return True
    for m in _AQL_CONDITION.finditer(condition):
        field = m.group(1)
        op = m.group(2).upper()
        val = m.group(4)

        if field.startswith("data-"):
            actual = node.attributes.get(field, "")
        elif field == "text":
            actual = node.text
        else:
            actual = node.attributes.get(field, "")

        try:
            num_actual = float(actual)
            num_val = float(val)
            if op in ("<", "LT"):
                return num_actual < num_val
            if op in (">", "GT"):
                return num_actual > num_val
            if op in ("<=", "LE"):
                return num_actual <= num_val
            if op in (">=", "GE"):
                return num_actual >= num_val
        except (ValueError, TypeError):
            pass

        if op == "CONTAINS":
            return val.lower() in actual.lower()
        if op in ("==", "="):
            return actual == val
        if op == "!=":
            return actual != val

    return True


def _get_field(node: Node, field: str) -> str:
    field = field.strip()
    if field.startswith("data-") or field.startswith("aria-"):
        return node.attributes.get(field, "")
    if field == "text":
        return node.text
    if field == "type":
        return node.type
    if field == "id":
        return node.attributes.get("id", "")
    if field in node.attributes:
        return node.attributes[field]
    # Look for named child
    child = node.find_one(field)
    if child:
        return child.text_content()
    return node.attributes.get(field, "")


def execute_aql(query_str: str, root: Node) -> dict:
    """Execute an AQL query string against a content root node."""
    results: List[dict] = []

    m = _AQL_QUERY.search(query_str)
    if not m:
        return {"error": "Could not parse AQL query", "results": []}

    qname = m.group(1)
    from_type = m.group(2)
    from_attrs = _parse_attrs(m.group(3) or "")
    select_fields = [f.strip() for f in m.group(4).split(",")]
    where_cond = m.group(5) or ""
    order_by = m.group(6)
    order_dir = (m.group(7) or "ASC").upper()
    limit = int(m.group(8)) if m.group(8) else None
    returns = m.group(9).lower()

    # Find matching nodes
    candidates = root.find(from_type)

    # Filter by from_attrs
    if from_attrs:
        candidates = [
            n
            for n in candidates
            if all(n.attributes.get(k) == v for k, v in from_attrs.items())
        ]

    # Apply WHERE
    if where_cond:
        candidates = [n for n in candidates if _eval_condition(n, where_cond)]

    # Extract fields
    for node in candidates:
        row: dict = {}
        for fld in select_fields:
            row[fld] = _get_field(node, fld)
        results.append(row)

    # ORDER BY
    if order_by and results:
        try:
            results.sort(
                key=lambda r: float(r.get(order_by, 0) or 0),
                reverse=(order_dir == "DESC"),
            )
        except (ValueError, TypeError):
            results.sort(
                key=lambda r: str(r.get(order_by, "")), reverse=(order_dir == "DESC")
            )

    # LIMIT
    if limit is not None:
        results = results[:limit]

    return {
        "query": qname,
        "returns": returns,
        "count": len(results),
        "results": results,
    }


def execute_named_query(doc: AxonDocument, query_name: str) -> dict:
    """Execute a pre-declared query from the document's queries/ directory."""
    if query_name not in doc.queries:
        return {"error": f"Query '{query_name}' not found in document"}
    return execute_aql(doc.queries[query_name], doc.content)


# ─────────────────────────────────────────────────────────────
# SECTION 16 — DIFF ENGINE (AXD)
# ─────────────────────────────────────────────────────────────


@dataclass
class AxdOperation:
    op: str  # INSERT, DELETE, REPLACE, MOVE, MODIFY_ATTR
    target_id: str
    args: dict = field(default_factory=dict)


def diff_trees(old_root: Node, new_root: Node) -> List[AxdOperation]:
    """Produce a list of AXD operations that transform old_root into new_root.
    This is a simplified structural diff — compares by node id."""
    ops: List[AxdOperation] = []

    def collect_by_id(root: Node) -> Dict[str, Node]:
        result: Dict[str, Node] = {}

        def walk(n: Node) -> None:
            nid = n.attributes.get("id")
            if nid:
                result[nid] = n
            for c in n.children:
                walk(c)

        walk(root)
        return result

    old_nodes = collect_by_id(old_root)
    new_nodes = collect_by_id(new_root)

    for nid, new_node in new_nodes.items():
        if nid not in old_nodes:
            ops.append(
                AxdOperation(
                    op="INSERT",
                    target_id=nid,
                    args={"axc": serialize_axc(new_node, indent=0)},
                )
            )
        else:
            old_node = old_nodes[nid]
            if old_node.text != new_node.text:
                ops.append(
                    AxdOperation(
                        op="REPLACE",
                        target_id=nid,
                        args={"axc": serialize_axc(new_node, indent=0)},
                    )
                )
            for k, v in new_node.attributes.items():
                if old_node.attributes.get(k) != v:
                    ops.append(
                        AxdOperation(
                            op="MODIFY_ATTR",
                            target_id=nid,
                            args={
                                "attribute": k,
                                "old": old_node.attributes.get(k, ""),
                                "new": v,
                            },
                        )
                    )

    for nid in old_nodes:
        if nid not in new_nodes:
            ops.append(AxdOperation(op="DELETE", target_id=nid))

    return ops


def serialize_delta(
    ops: List[AxdOperation],
    delta_id: int,
    parent_revision: int,
    author: str,
    summary: str,
    parent_content_hash: str,
    resulting_content_hash: str,
) -> dict:
    return {
        "delta_id": delta_id,
        "parent_revision": parent_revision,
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": author,
        "change_summary": summary,
        "content_diff": [
            {"op": o.op, "target_id": o.target_id, "args": o.args} for o in ops
        ],
        "parent_content_hash": parent_content_hash,
        "resulting_content_hash": resulting_content_hash,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 17 — CLI
# ─────────────────────────────────────────────────────────────


def _cmd_encode(args: argparse.Namespace) -> None:
    if args.input.endswith(".axc"):
        with open(args.input, "r", encoding="utf-8") as f:
            axc_text = f.read()
        doc = convert_axc_string(
            axc_text,
            title=args.title or pathlib.Path(args.input).stem,
            document_type=args.type,
        )
    elif args.input.endswith(".pdf"):
        doc = convert_pdf(args.input, title=args.title, document_type=args.type)
    elif args.input.endswith(".json"):
        doc = convert_json_sdf(
            args.input, title=args.title or "Document", document_type=args.type
        )
    else:
        print(f"Unsupported input format: {args.input}")
        return

    output = args.output or args.input.replace(pathlib.Path(args.input).suffix, ".axon")
    encode_archive(doc, output)
    print(f"Encoded: {output}")


def _cmd_decode(args: argparse.Namespace) -> None:
    doc = decode_archive(args.input, verify=not args.no_verify)
    print(f"Decoded: {args.input}")
    print(f"  Title:    {doc.manifest.title}")
    print(f"  Type:     {doc.manifest.document_type}")
    print(f"  Revision: {doc.manifest.revision}")
    print(f"  Language: {doc.manifest.language}")
    print(f"  Authors:  {[a.get('name') for a in doc.manifest.authors]}")


def _cmd_validate(args: argparse.Namespace) -> None:
    doc = decode_archive(args.input, verify=False)
    result = validate(doc)
    print(result)


def _cmd_render(args: argparse.Namespace) -> None:
    doc = decode_archive(args.input)
    if args.format == "html":
        output = render_html(doc)
        ext = ".html"
    else:
        output = render_text(doc)
        ext = ".txt"

    out_path = args.output or args.input.replace(".axon", ext)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Rendered: {out_path}")


def _cmd_query(args: argparse.Namespace) -> None:
    doc = decode_archive(args.input)
    if args.named:
        result = execute_named_query(doc, args.query)
    else:
        result = execute_aql(args.query, doc.content)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _cmd_diff(args: argparse.Namespace) -> None:
    old_doc = decode_archive(args.old)
    new_doc = decode_archive(args.new)
    ops = diff_trees(old_doc.content, new_doc.content)
    print(f"Operations: {len(ops)}")
    for op in ops:
        print(f"  {op.op:15s} id={op.target_id}")


def _cmd_info(args: argparse.Namespace) -> None:
    with zipfile.ZipFile(args.input, "r") as zf:
        print(f"Archive: {args.input}")
        print("Files:")
        for name in sorted(zf.namelist()):
            info = zf.getinfo(name)
            print(f"  {name:<50s}  {info.file_size:>8d} bytes")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axon",
        description="AXON Document Format — Reference Implementation v1.0",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # encode
    p_enc = sub.add_parser("encode", help="Convert a file to .axon archive")
    p_enc.add_argument("input", help="Input file (.axc, .pdf, .json)")
    p_enc.add_argument("-o", "--output", help="Output .axon path")
    p_enc.add_argument("--title", help="Document title")
    p_enc.add_argument("--type", default="article.research", help="Document type")
    p_enc.set_defaults(func=_cmd_encode)

    # decode
    p_dec = sub.add_parser("decode", help="Inspect a .axon archive")
    p_dec.add_argument("input", help="Input .axon file")
    p_dec.add_argument(
        "--no-verify", action="store_true", help="Skip hash verification"
    )
    p_dec.set_defaults(func=_cmd_decode)

    # validate
    p_val = sub.add_parser("validate", help="Validate a .axon archive")
    p_val.add_argument("input", help="Input .axon file")
    p_val.set_defaults(func=_cmd_validate)

    # render
    p_ren = sub.add_parser("render", help="Render a .axon archive to HTML or text")
    p_ren.add_argument("input", help="Input .axon file")
    p_ren.add_argument("-f", "--format", choices=["html", "text"], default="html")
    p_ren.add_argument("-o", "--output", help="Output file path")
    p_ren.set_defaults(func=_cmd_render)

    # query
    p_qry = sub.add_parser("query", help="Execute an AQL query")
    p_qry.add_argument("input", help="Input .axon file")
    p_qry.add_argument("query", help="AQL query string or query name")
    p_qry.add_argument(
        "--named", action="store_true", help="Execute a pre-declared named query"
    )
    p_qry.set_defaults(func=_cmd_query)

    # diff
    p_dif = sub.add_parser("diff", help="Diff two .axon archives")
    p_dif.add_argument("old", help="Old .axon file")
    p_dif.add_argument("new", help="New .axon file")
    p_dif.set_defaults(func=_cmd_diff)

    # info
    p_inf = sub.add_parser("info", help="List contents of a .axon archive")
    p_inf.add_argument("input", help="Input .axon file")
    p_inf.set_defaults(func=_cmd_info)

    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
