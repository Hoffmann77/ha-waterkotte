"""The base entity (and entity description) of the Waterkotte Heatpump integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag

if TYPE_CHECKING:
    from . import WKHPDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class WKHPEntityDescription(EntityDescription):
    """The tag of the heat pump, that provides the value of the entity."""

    tag: WKHPTag | None = None
    # the entity is enabled by default, when this feature has been selected during the setup
    feature: str | None = None


class WKHPBaseEntity(CoordinatorEntity["WKHPDataUpdateCoordinator"]):
    _attr_has_entity_name = True

    entity_description: WKHPEntityDescription

    def __init__(self, coordinator: WKHPDataUpdateCoordinator, description: WKHPEntityDescription) -> None:
        super().__init__(coordinator, context=description.tag)
        self._attr_translation_key = description.key.lower()
        self._attr_unique_id = f"{coordinator.unique_id_base}_{description.key}".lower()
        self._attr_device_info = coordinator.device_info
        self.entity_description = description

        # check, if the feature should be enabled by default (if activated during setup)
        if not description.entity_registry_enabled_default and description.feature is not None:
            if description.feature in coordinator.available_features:
                self._attr_entity_registry_enabled_default = True

    @property
    def available(self) -> bool:
        """The entity is unavailable, when the value of its tag could not be read in the last update."""
        return super().available and self.wkhp_tag in (self.coordinator.data or {})

    @property
    def wkhp_tag(self):
        """The tag of the heat pump, that provides the value of this entity."""
        return self.entity_description.tag

    @property
    def _tag_value(self):
        """The current value of the tag - or None, if the heat pump did not provide a value"""
        value = (self.coordinator.data or {}).get(self.wkhp_tag, {}).get("value")
        return None if value == "" else value
