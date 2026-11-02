"""Daily and lifetime energy counters reported by MOVA devices."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy

from .entity import MovaEnergySensorEntityDescription

ENTITY_DESCRIPTIONS: tuple[MovaEnergySensorEntityDescription, ...] = (
    MovaEnergySensorEntityDescription(
        key="pv_daily_energy",
        translation_key="pv_daily_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        value_fn=lambda data: data.get("pv_daily_energy"),
    ),
    MovaEnergySensorEntityDescription(
        key="grid_import_daily_energy",
        translation_key="grid_import_daily_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        value_fn=lambda data: data.get("grid_import_daily_energy"),
    ),
    MovaEnergySensorEntityDescription(
        key="grid_export_daily_energy",
        translation_key="grid_export_daily_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        value_fn=lambda data: data.get("grid_export_daily_energy"),
    ),
)

PV_TOTAL_ENTITY_DESCRIPTION = MovaEnergySensorEntityDescription(
    key="pv_total_energy",
    translation_key="pv_total_energy",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    value_fn=lambda data: data.get("pv_total_energy"),
)
