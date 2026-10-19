"""Create and verify a small in-toto/SLSA-style provenance statement for Gate 12."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROVENANCE_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


def _image_parts(image_reference: str) -> tuple[str, str]:
    name, separator, digest = image_reference.rpartition("@sha256:")
    if not separator or len(digest) != 64:
        raise ValueError("image reference must contain a 64-character sha256 digest")
    int(digest, 16)
    return name, digest


def build_statement(
    *,
    repository: str,
    commit: str,
    builder: str,
    workflow: str,
    image_reference: str,
    dockerfile: str,
    build_inputs: list[str],
) -> dict[str, Any]:
    image_name, image_digest = _image_parts(image_reference)
    return {
        "_type": PROVENANCE_TYPE,
        "subject": [{"name": image_name, "digest": {"sha256": image_digest}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "buildDefinition": {
                "buildType": "https://slsa.dev/container/v1",
                "externalParameters": {
                    "repository": repository,
                    "commit": commit,
                    "dockerfile": dockerfile,
                    "buildInputs": build_inputs,
                },
                "internalParameters": {"workflow": workflow},
            },
            "runDetails": {"builder": {"id": builder}},
        },
    }


def verify_statement(path: Path, *, image_reference: str, commit: str) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    image_name, image_digest = _image_parts(image_reference)
    subject = document.get("subject")
    assert document.get("_type") == PROVENANCE_TYPE
    assert document.get("predicateType") == PREDICATE_TYPE
    assert subject == [{"name": image_name, "digest": {"sha256": image_digest}}]
    params = document["predicate"]["buildDefinition"]["externalParameters"]
    assert params["commit"] == commit
    print("PROVENANCE: VERIFIED")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--repository", required=True)
    create.add_argument("--commit", required=True)
    create.add_argument("--builder", required=True)
    create.add_argument("--workflow", required=True)
    create.add_argument("--image-reference", required=True)
    create.add_argument("--dockerfile", required=True)
    create.add_argument("--build-input", action="append", default=[])
    verify = subparsers.add_parser("verify")
    verify.add_argument("--path", type=Path, required=True)
    verify.add_argument("--image-reference", required=True)
    verify.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.command == "create":
        document = build_statement(
            repository=args.repository,
            commit=args.commit,
            builder=args.builder,
            workflow=args.workflow,
            image_reference=args.image_reference,
            dockerfile=args.dockerfile,
            build_inputs=args.build_input,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"PROVENANCE: CREATED {args.output}")
        return 0
    verify_statement(args.path, image_reference=args.image_reference, commit=args.commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
