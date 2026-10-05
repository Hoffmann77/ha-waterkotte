"""Read-only copies of the entities, that can change settings of the heat pump (switches, numbers and selects).

The copies can be shown on a dashboard without the risk, that a user changes a setting by accident. They are
added by the option 'add_readonly_copies' and use the same tags as the original entities (so the heat pump is
not polled for additional values).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.icon import async_get_icons
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN
from .entity import WKHPBaseEntity, WKHPEntityDescription

if TYPE_CHECKING:
    from .coordinator import WKHPDataUpdateCoordinator

# the suffix of the key (and so of the unique_id) of a read-only copy
READONLY_SUFFIX = "_READONLY"
# the translation key of all read-only copies - the name of the original entity is a placeholder
READONLY_TRANSLATION_KEY = "readonly_copy"


class ReadOnlyTexts:
    """The names (and the icons) of the original entities - used for the read-only copies."""

    def __init__(self, translations: Mapping[str, str], icons: Mapping[str, Any]) -> None:
        self._translations = translations
        self._icons = icons

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> ReadOnlyTexts:
        translations = await async_get_translations(hass, hass.config.language, "entity", {DOMAIN})
        icons = await async_get_icons(hass, "entity", {DOMAIN})
        return cls(translations, icons.get(DOMAIN, {}))

    def name(self, platform: str, key: str) -> str:
        return self._translations.get(f"component.{DOMAIN}.entity.{platform}.{key}.name", key)

    def option(self, platform: str, key: str, option: str) -> str:
        return self._translations.get(f"component.{DOMAIN}.entity.{platform}.{key}.state.{option}", option)

    def icons(self, platform: str, key: str) -> Mapping[str, Any]:
        return self._icons.get(platform, {}).get(key, {})


class WKHPReadOnlyEntity(WKHPBaseEntity):
    """The read-only copy of an entity of another platform (e.g. a switch shown as binary sensor)."""

    def __init__(self, coordinator: WKHPDataUpdateCoordinator, description: WKHPEntityDescription,
                 original_platform: str, texts: ReadOnlyTexts) -> None:
        super().__init__(coordinator, description)
        # the translation key, name and icon of the original entity
        self._original_platform = original_platform
        self._original_key = description.key.removesuffix(READONLY_SUFFIX).lower()
        self._texts = texts
        self._attr_translation_key = READONLY_TRANSLATION_KEY
        self._attr_translation_placeholders = {"name": texts.name(original_platform, self._original_key)}

    @property
    def _icon_state(self) -> str:
        """The state of the original entity - its icon can depend on the state."""
        return str(self.state)

    @property
    def icon(self) -> str | None:
        icons = self._texts.icons(self._original_platform, self._original_key)
        return icons.get("state", {}).get(self._icon_state, icons.get("default"))
