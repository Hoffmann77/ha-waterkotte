"""Tests for the translations (translations/en.json is the source of the texts, de.json must be complete)."""
import json
import re
from pathlib import Path

import pytest
import yaml

from custom_components.waterkotte_heatpump import binary_sensor, number, select, sensor, switch

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "waterkotte_heatpump"
TRANSLATIONS = {lang: json.loads((INTEGRATION / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
                for lang in ("en", "de")}
DESCRIPTIONS = {
    "binary_sensor": binary_sensor.BINARY_SENSORS,
    "number": number.NUMBER_SENSORS,
    "select": select.SELECT_SENSORS,
    "sensor": sensor.SENSOR_SENSORS,
    "switch": switch.SWITCH_SENSORS,
}


def _paths(data: dict, prefix: str = "") -> set[str]:
    paths = set()
    for key, value in data.items():
        if isinstance(value, dict):
            paths |= _paths(value, f"{prefix}{key}.")
        else:
            paths.add(f"{prefix}{key}")
    return paths


def test_languages_complete() -> None:
    """Test that the German translation has the same texts as the English one."""
    assert _paths(TRANSLATIONS["de"]) == _paths(TRANSLATIONS["en"])


@pytest.mark.parametrize("platform", DESCRIPTIONS)
def test_entity_names(platform: str) -> None:
    """Test that every entity has a name - and that there are no names of removed entities."""
    keys = {description.key.lower() for description in DESCRIPTIONS[platform]}
    names = TRANSLATIONS["en"]["entity"][platform]
    assert keys - set(names) == set(), "entities without name"
    assert set(names) - keys == set(), "names of removed entities"
    assert all("name" in names[key] for key in keys)


def test_services() -> None:
    """Test that every service (and every field of a service) is translated."""
    services = yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8"))
    translated = TRANSLATIONS["en"]["services"]
    assert set(services) == set(translated)
    for service, spec in services.items():
        assert {"name", "description"} <= set(translated[service])
        assert set(spec.get("fields", {})) == set(translated[service].get("fields", {})), service


def test_exceptions() -> None:
    """Test that every translation key of an exception, that is raised in the code, is translated."""
    code = "\n".join(path.read_text(encoding="utf-8") for path in INTEGRATION.glob("*.py"))
    used = set(re.findall(r'translation_key="([a-z_]+)"', code))
    assert used
    assert used - set(TRANSLATIONS["en"]["exceptions"]) == set()
