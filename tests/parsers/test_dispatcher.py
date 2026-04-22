"""Unit tests for ``backend.parsers.dispatcher.Dispatcher``.

Pin two contracts:

1. **Registry coverage** — every legacy ``custom_parser`` value handled
   by the old ``parse_output()`` if/elif ladder is registered.
2. **Routing parity** — for the same inputs, ``Dispatcher().parse()``
   produces the same dict as the legacy ``parse_output()``.
"""

from __future__ import annotations

import pytest

from backend.parsers.dispatcher import Dispatcher

# Mirrors the legacy if/elif ladder in backend/parse_output.py exactly.
LEGACY_CUSTOM_PARSERS: tuple[str, ...] = (
    "arista_cpu",
    "arista_disk",
    "arista_interface_description",
    "arista_interface_status",
    "arista_isis_adjacency",
    "arista_power",
    "arista_transceiver",
    "arista_uptime",
    "cisco_interface_description",
    "cisco_interface_detailed",
    "cisco_interface_show_mtu",
    "cisco_interface_status",
    "cisco_isis_interface_brief",
    "cisco_nxos_transceiver",
    "cisco_power",
    "cisco_system_uptime",
)


class TestRegistryCoverage:
    """Every legacy custom_parser value is registered."""

    @pytest.mark.parametrize("name", LEGACY_CUSTOM_PARSERS)
    def test_legacy_custom_parser_is_registered(self, name: str) -> None:
        assert Dispatcher().has(name), (
            f"custom_parser={name!r} must be registered in the dispatcher; "
            "the legacy parse_output() if/elif ladder included this branch."
        )

    def test_introspection_lists_all_in_alphabetical_order(self) -> None:
        names = Dispatcher().custom_parsers()
        # All legacy names included
        assert set(LEGACY_CUSTOM_PARSERS).issubset(set(names))
        # Sorted
        assert names == sorted(names)


class TestRoutingFallbacks:
    def test_none_config_returns_empty(self) -> None:
        assert Dispatcher().parse("any", {"a": 1}, None) == {}

    def test_unknown_custom_parser_falls_back_to_field_engine(self) -> None:
        # Unknown name → fall back to GenericFieldEngine, which honours fields
        cfg = {
            "custom_parser": "made_up_vendor_parser",
            "fields": [{"name": "v", "json_path": "a"}],
        }
        assert Dispatcher().parse("any", {"a": 42}, cfg) == {"v": 42}

    def test_no_custom_parser_uses_field_engine(self) -> None:
        cfg = {"fields": [{"name": "v", "json_path": "a"}]}
        assert Dispatcher().parse("any", {"a": 7}, cfg) == {"v": 7}


class TestParityWithLegacyParseOutput:
    """For each registered parser, dispatcher output == legacy parse_output output."""

    @pytest.mark.parametrize("name", LEGACY_CUSTOM_PARSERS)
    def test_parity_with_empty_input(self, name: str) -> None:
        from backend.parse_output import parse_output

        cfg = {"custom_parser": name}
        legacy = parse_output("anycmd", {}, cfg)
        new = Dispatcher().parse("anycmd", {}, cfg)
        assert new == legacy, (
            f"dispatch parity violated for custom_parser={name!r}"
        )

    def test_parity_for_field_engine_branch(self) -> None:
        from backend.parse_output import parse_output

        cfg = {"fields": [{"name": "v", "json_path": "a.b"}]}
        data = {"a": {"b": 99}}
        assert Dispatcher().parse("c", data, cfg) == parse_output("c", data, cfg)


class TestCustomRegistry:
    def test_constructor_accepts_user_registry(self) -> None:
        sentinel = lambda raw: {"sentinel": True, "raw": raw}  # noqa: E731
        d = Dispatcher(registry={"my_kind": sentinel})
        assert d.has("my_kind")
        assert d.parse("c", "abc", {"custom_parser": "my_kind"}) == {
            "sentinel": True,
            "raw": "abc",
        }

    def test_user_registry_replaces_defaults(self) -> None:
        # Empty registry → every legacy custom_parser falls back to field engine
        d = Dispatcher(registry={})
        assert not d.has("arista_uptime")
        # With no fields and a "registered" but missing custom_parser,
        # it falls back to GenericFieldEngine which sees no fields → {}
        assert d.parse("c", {}, {"custom_parser": "arista_uptime"}) == {}

    def test_registry_is_defensively_copied(self) -> None:
        # External mutation of the constructor input must not affect the engine
        ext: dict = {"k": lambda raw: {"k": 1}}
        d = Dispatcher(registry=ext)
        ext["k"] = lambda raw: {"k": "changed"}
        # Dispatcher kept its own copy of the original callable
        assert d.parse("c", None, {"custom_parser": "k"}) == {"k": 1}
