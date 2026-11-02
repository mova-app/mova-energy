"""Connectivity reported by the MOVA electricity meter."""

from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

ENTITY_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="meter_online",
        translation_key="meter_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class MovaEnergyMeterSensor(BinarySensorEntity, MovaEnergyEntity):
    """Report meter connectivity independently of the main device connection."""

    @property
    def is_on(self) -> bool | None:
        """Return the meter's online flag, or None if not reported."""
        return self.coordinator.data.get(self.entity_description.key)
