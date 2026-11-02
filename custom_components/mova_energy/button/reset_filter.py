"""Reset filter button for mova_energy."""

from custom_components.mova_energy.entity import MovaEnergyEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.button.const import ButtonDeviceClass
from homeassistant.const import EntityCategory

ENTITY_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="reset_filter",
        translation_key="reset_filter",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
    ),
)


class MovaEnergyButton(ButtonEntity, MovaEnergyEntity):
    """Button that resets the device's filter timer."""

    async def async_press(self) -> None:
        """Reset the filter timer on the device."""
        await self._async_write(lambda client: client.async_reset_filter(), "reset_filter_failed")
