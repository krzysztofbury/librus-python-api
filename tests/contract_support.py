"""Test-owned OpenAPI validation and central route-catalogue parity helpers."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from openapi_spec_validator import OpenAPIV30SpecValidator

from librus_python_api import __version__
from librus_python_api.config import UPSTREAM_ORIGINS, Endpoint

SPEC_PATH = Path(__file__).resolve().parents[1] / "contracts/upstream.openapi.yaml"
HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def reject_external_references(value: Any) -> None:
    """Walk local trusted contract data before the schema validator resolves refs."""
    pending = [value]
    visited: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, (dict, list)):
            if id(item) in visited:
                continue
            visited.add(id(item))
        if isinstance(item, dict):
            reference = item.get("$ref")
            if reference is not None and (
                not isinstance(reference, str) or not reference.startswith("#/")
            ):
                raise ValueError("Only local OpenAPI references are allowed")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def check_contract(spec: dict[str, Any], endpoints: Mapping[str, Endpoint]) -> None:
    reject_external_references(spec)
    OpenAPIV30SpecValidator(spec).validate()
    if any("$ref" in item for item in spec["paths"].values()):
        raise ValueError("Path-item references are not supported")
    if spec["info"]["version"] != __version__:
        raise ValueError("Contract version differs from the package version")
    expected: dict[tuple[str, str, str], Endpoint] = {}
    for name, endpoint in endpoints.items():
        if name != endpoint.operation_id:
            raise ValueError("Catalogue key differs from operation ID")
        route = (endpoint.path, endpoint.method.lower(), name)
        if route in expected:
            raise ValueError("Duplicate catalogue route")
        expected[route] = endpoint
    physical = {
        (path, method): operation
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }
    if physical.keys() != {(p, m) for p, m, _ in expected}:
        raise ValueError("OpenAPI paths/methods differ from the route catalogue")
    actual = {}
    for (path, method), operation in physical.items():
        variants = operation.get("x-request-variants", [])
        if not isinstance(variants, list):
            raise ValueError("Request variants must be explicit operations")
        for entry in [operation, *variants]:
            if not isinstance(entry, dict) or not isinstance(
                entry.get("operationId"), str
            ):
                raise ValueError("Request variant needs an operation ID")
            variant_key = (path, method, entry["operationId"])
            if variant_key in actual:
                raise ValueError("Duplicate contract operation")
            actual[variant_key] = entry
            if entry is not operation:
                variant_spec = deepcopy(spec)
                variant_spec["paths"][path][method] = entry
                OpenAPIV30SpecValidator(variant_spec).validate()
    if actual.keys() != expected.keys():
        raise ValueError(
            "Contract metadata mismatch: undeclared request variant or operation"
        )
    for route, endpoint in expected.items():
        operation = actual[route]
        required = {
            "operationId": endpoint.operation_id,
            "x-side-effect": endpoint.side_effect.value,
            "x-retry-safe": endpoint.retry_safe,
            "x-evidence": endpoint.evidence.value,
            "x-origin": endpoint.origin,
            "x-upstream-origin": UPSTREAM_ORIGINS[endpoint.origin],
        }
        for key, value in required.items():
            if type(operation.get(key)) is not type(value) or operation[key] != value:
                raise ValueError(f"Contract metadata mismatch: {key}")
        note = operation.get("x-evidence-note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Each operation needs a nonempty evidence note")
