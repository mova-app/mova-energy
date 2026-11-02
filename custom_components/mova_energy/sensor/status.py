"""Battery measurements and operating status for MOVA energy devices."""

from custom_components.mova_energy.const import RUN_STATUS_OPTIONS
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature

from .entity import MovaEnergySensorEntityDescription

ENTITY_DESCRIPTIONS: tuple[MovaEnergySensorEntityDescription, ...] = (
    MovaEnergySensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("battery_soc"),
    ),
    MovaEnergySensorEntityDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda data: data.get("battery_temperature"),
    ),
    MovaEnergySensorEntityDescription(
        key="run_status",
        translation_key="run_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(RUN_STATUS_OPTIONS.values()),
        value_fn=lambda data: data.get("run_status"),
    ),
    MovaEnergySensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("firmware_version"),
    ),
)
