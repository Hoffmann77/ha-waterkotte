"""Tests for the entity descriptions."""
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.waterkotte_heatpump.sensor import SENSOR_SENSORS


def test_energy_state_class() -> None:
    """Test that the energy sensors are totals (Home Assistant rejects 'measurement' for energy)."""
    invalid = [description.key for description in SENSOR_SENSORS
               if description.device_class == SensorDeviceClass.ENERGY
               and description.state_class not in (SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING)]
    assert invalid == []
