"""Power sensor descriptions for mova_energy."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPower

from .entity import MovaEnergySensorEntityDescription

ENTITY_DESCRIPTIONS: tuple[MovaEnergySensorEntityDescription, ...] = (
    MovaEnergySensorEntityDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("pv_power"),
    ),
    MovaEnergySensorEntityDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("battery_power"),
    ),
    MovaEnergySensorEntityDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("grid_power"),
    ),
    MovaEnergySensorEntityDescription(
        key="load_power",
        translation_key="load_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("load_power"),
    ),
    MovaEnergySensorEntityDescription(
        key="eps_power",
        translation_key="eps_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("eps_power"),
    ),
)
