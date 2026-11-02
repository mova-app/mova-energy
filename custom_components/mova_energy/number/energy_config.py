"""Energy configuration numbers for local devices and cloud device groups."""

import math

from custom_components.mova_energy.const import DOMAIN, LOCAL_CONFIG_NUMBERS
from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.components.number.const import NumberDeviceClass, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.exceptions import ServiceValidationError

ENTITY_DESCRIPTIONS: tuple[NumberEntityDescription, ...] = tuple(
    NumberEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.POWER if maximum == 65535 else None,
        native_unit_of_measurement=UnitOfPower.WATT if maximum == 65535 else PERCENTAGE,
        native_min_value=minimum,
        native_max_value=maximum,
        native_step=1,
        mode=NumberMode.BOX,
    )
    for key, (_, minimum, maximum) in LOCAL_CONFIG_NUMBERS.items()
)


class MovaEnergyConfigNumber(NumberEntity, MovaEnergyEntity):
    """Integer setting reported by configuration readback."""

    @property
    def native_value(self) -> float | None:
        """Return the actual setting from the device readback."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Write an integer without silently truncating fractional requests."""
        if isinstance(value, bool) or not math.isfinite(value) or value != int(value):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_config_value")
        await self.coordinator.async_write_config(self.entity_description.key, int(value))
