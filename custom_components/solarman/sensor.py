from __future__ import annotations

import logging

from typing import Any

from homeassistant.components.template.sensor import SensorTemplate
from homeassistant.components.template.sensor import TriggerSensorEntity
from homeassistant.helpers.template import Template

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.components.sensor import RestoreSensor, SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *
from .common import *
from .services import *
from .entity import create_entity, SolarmanEntity

_LOGGER = logging.getLogger(__name__)

_PLATFORM = get_current_file_name(__name__)

def _create_entity(coordinator, description, options):
    if "artificial" in description:
        match description["artificial"]:
            case "interval":
                return SolarmanIntervalSensor(coordinator, description)

    if "persistent" in description:
        return SolarmanPersistentSensor(coordinator, description)

    if "restore" in description or "ensure_increasing" in description:
        return SolarmanRestoreSensor(coordinator, description)

    return SolarmanSensor(coordinator, description)

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    _LOGGER.debug(f"async_setup_entry: {config.options}")
    coordinator = hass.data[DOMAIN][config.entry_id]

    descriptions = coordinator.inverter.get_entity_descriptions()

    _LOGGER.debug(f"async_setup: async_add_entities")

    async_add_entities(create_entity(lambda x: _create_entity(coordinator, x, config.options), d) for d in descriptions if (is_platform(d, _PLATFORM) and not "configurable" in d))

    return True

async def async_unload_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    _LOGGER.debug(f"async_unload_entry: {config.options}")

    return True

class SolarmanSensorEntity(SolarmanEntity, SensorEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(coordinator, sensor)
        if "state_class" in sensor and (state_class := sensor["state_class"]):
            self._attr_state_class = state_class

class SolarmanIntervalSensor(SolarmanSensorEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(coordinator, sensor)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = "s"
        self._attr_state_class = "duration"
        self._attr_icon = "mdi:update"

    @property
    def available(self) -> bool:
        return self._attr_native_value > 0

    def update(self):
        self.set_state(self.coordinator.inverter.state_interval.total_seconds())

class SolarmanSensor(SolarmanSensorEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(coordinator, sensor)
        self._sensor_ensure_increasing = "ensure_increasing" in sensor

class SolarmanRestoreSensor(SolarmanSensor, RestoreSensor):
    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_sensor_data.native_value
            self._attr_native_unit_of_measurement = last_sensor_data.native_unit_of_measurement

    def set_state(self, state):
        if self._sensor_ensure_increasing and self._attr_native_value and self._attr_native_value > state > 0:
            return

        self._attr_state = self._attr_native_value = state

class SolarmanPersistentSensor(SolarmanRestoreSensor):
    @property
    def available(self) -> bool:
        return True
