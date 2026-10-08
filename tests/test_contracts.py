import re
from copy import deepcopy
from typing import Any

import pytest
import yaml
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from librus_python_api import __version__
from librus_python_api.config import ENDPOINTS, Endpoint, Evidence, SideEffect
from tests.contract_support import SPEC_PATH, check_contract

CHANGELOG = SPEC_PATH.parents[1] / "CHANGELOG.md"


def test_the_package_version_has_a_dated_changelog_entry() -> None:
    # The release gate refuses a tag without one; catch it before merging.
    heading = rf"^## {re.escape(__version__)} \([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\)"
    assert re.search(heading, CHANGELOG.read_text(), re.MULTILINE)


def fixture_contract() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Synthetic contract", "version": __version__},
        "paths": {
            "/fixture/identity": {
                "get": {
                    "operationId": "fixture_identity",
                    "x-side-effect": "none",
                    "x-retry-safe": True,
                    "x-evidence": "synthetic_only",
                    "x-origin": "synergia",
                    "x-upstream-origin": "https://synergia.librus.pl",
                    "x-evidence-note": "Synthetic fixture, not Librus data.",
                    "responses": {
                        "200": {
                            "description": "Fixture HTML",
                            "content": {"text/html": {"schema": {"type": "string"}}},
                        }
                    },
                }
            }
        },
    }


def fixture_catalogue() -> dict[str, Endpoint]:
    return {
        "fixture_identity": Endpoint(
            "fixture_identity",
            "GET",
            "/fixture/identity",
            SideEffect.NONE,
            True,
            Evidence.SYNTHETIC_ONLY,
        )
    }


def test_shipped_openapi_matches_enabled_routes() -> None:
    check_contract(yaml.safe_load(SPEC_PATH.read_text()), ENDPOINTS)


def test_html_contract_can_be_validated_without_normalized_json_fiction() -> None:
    check_contract(fixture_contract(), fixture_catalogue())


@pytest.mark.parametrize("change", ["missing_route", "extra_route", "changed_method"])
def test_route_drift_fails_validation(change: str) -> None:
    spec = fixture_contract()
    operation = spec["paths"]["/fixture/identity"].pop("get")
    if change == "extra_route":
        spec["paths"]["/fixture/identity"]["get"] = deepcopy(operation)
        operation["operationId"] = "extra_fixture"
        spec["paths"]["/fixture/extra"] = {"get": operation}
    elif change == "changed_method":
        spec["paths"]["/fixture/identity"]["post"] = operation
    with pytest.raises(ValueError, match="paths/methods differ"):
        check_contract(spec, fixture_catalogue())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("operationId", "wrong_identity"),
        ("x-side-effect", "mark_read"),
        ("x-retry-safe", False),
        ("x-retry-safe", 1),
        ("x-evidence", "independently_observed"),
    ],
)
def test_policy_or_evidence_drift_fails_validation(key: str, value: object) -> None:
    spec = fixture_contract()
    spec["paths"]["/fixture/identity"]["get"][key] = value
    with pytest.raises(ValueError, match="metadata mismatch"):
        check_contract(spec, fixture_catalogue())


def test_endpoint_requires_evidence_note() -> None:
    spec = fixture_contract()
    del spec["paths"]["/fixture/identity"]["get"]["x-evidence-note"]
    with pytest.raises(ValueError, match="evidence note"):
        check_contract(spec, fixture_catalogue())


def test_external_schema_is_rejected_before_resolution() -> None:
    spec = fixture_contract()
    spec["components"] = {
        "schemas": {"Foreign": {"$ref": "https://example.invalid/private-schema"}}
    }
    with pytest.raises(ValueError, match="Only local OpenAPI references"):
        check_contract(spec, fixture_catalogue())


def test_referenced_path_cannot_hide_an_undocumented_operation() -> None:
    spec = fixture_contract()
    spec["x-fixture-path"] = spec["paths"]["/fixture/identity"]
    spec["paths"]["/fixture/identity"] = {"$ref": "#/x-fixture-path"}
    with pytest.raises(ValueError, match="Path-item references are not supported"):
        check_contract(spec, {})


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "wrong_effect", "retry", "wrong_form", "wrong_type"],
)
def test_shared_route_send_variant_is_explicit_validated_and_cannot_drift(
    change: str,
) -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text())
    operation = spec["paths"]["/wiadomosci/1/6"]["post"]
    variant = operation["x-request-variants"][0]
    if change == "missing":
        del operation["x-request-variants"]
    elif change == "duplicate":
        operation["x-request-variants"].append(deepcopy(variant))
    elif change == "wrong_effect":
        variant["x-side-effect"] = "select_view"
    elif change == "retry":
        variant["x-retry-safe"] = True
    elif change == "wrong_form":
        variant["requestBody"]["content"]["application/x-www-form-urlencoded"][
            "schema"
        ]["type"] = "invalid-type"
    else:
        operation["x-request-variants"] = {}
    with pytest.raises((ValueError, OpenAPIValidationError)):
        check_contract(spec, ENDPOINTS)
