from __future__ import annotations

import logging

from typing import Any

from homeassistant.core import callback
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.typing import UNDEFINED, StateType, UndefinedType

from .const import *
from .common import *
from .services import *
from .coordinator import InverterCoordinator

_LOGGER = logging.getLogger(__name__)

def create_entity(creator, description):
    try:
        entity = creator(description)

        entity.update()

        return entity
    except BaseException as e:
        _LOGGER.error(f"Configuring {description} failed. [{format_exception(e)}]")
        raise

class SolarmanCoordinatorEntity(CoordinatorEntity[InverterCoordinator]):
    def __init__(self, coordinator: InverterCoordinator):
        super().__init__(coordinator)
        self._attr_device_info = self.coordinator.inverter.device_info
        self._attr_extra_state_attributes = {}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.inverter.available()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.update()
        self.async_write_ha_state()

    def get_data_state(self, name):
        return self.coordinator.data[name]["state"]

    def get_data_value(self, name):
        return self.coordinator.data[name]["value"]

    def get_data(self, name, default):
        if name in self.coordinator.data:
                return self.get_data_state(name)

        return default

    def set_state(self, state):
        self._attr_state = self._attr_native_value = state

    def update(self):
        if self.description_name in self.coordinator.data and (data := self.coordinator.data[self.description_name]):
            self.set_state(data["state"])
            if "value" in data:
                self._attr_extra_state_attributes["value"] = data["value"]
            if self.attributes:
                if "inverse" in self.attributes and self._attr_native_value:
                    self._attr_extra_state_attributes["−x"] = -self._attr_native_value
                for attr in filter(lambda a: a in self.coordinator.data, self.attributes):
                    self._attr_extra_state_attributes[attr.replace(f"{self.description_name} ", "")] = self.get_data_state(attr)

class SolarmanEntity(SolarmanCoordinatorEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(coordinator)
        self.description_name = sensor["name"]
        self.description_entity_id = sensor.get("entity_id")
        self.description_unique_id = self.description_entity_id if self.description_entity_id else self.description_name

        self._attr_entity_registry_enabled_default = not "disabled" in sensor
        self._attr_entity_registry_visible_default = not "hidden" in sensor

        self._attr_name = "{} {}".format(self.coordinator.inverter.name, self.description_name) if self.description_name else self.coordinator.inverter.name

        self._attr_unique_id = "{}_{}_{}".format(self.coordinator.inverter.name, self.coordinator.inverter.serial, self.description_unique_id) if self.description_unique_id else "{}_{}".format(self.coordinator.inverter.name, self.coordinator.inverter.serial)

        if self.description_entity_id:
            self.entity_id = "{}.{}_{}".format(platform, self.coordinator.inverter.name, self.description_entity_id)
        if translation_key := get_attr(sensor, "translation_key") or (translation_key := self.description_name.lower().replace(" ", "_")):
            self._attr_translation_key = translation_key
        if entity_category := get_attr(sensor, "category") or (entity_category := get_attr(sensor, "entity_category")):
            self._attr_entity_category = entity_category
        if device_class := get_attr(sensor, "class") or (device_class := get_attr(sensor, "device_class")):
            self._attr_device_class = device_class
        if unit_of_measurement := get_attr(sensor, "uom") or (unit_of_measurement := get_attr(sensor, "unit_of_measurement")):
            self._attr_native_unit_of_measurement = unit_of_measurement
        if options := get_attr(sensor, "options"):
            self._attr_options = options
            self._attr_extra_state_attributes = self._attr_extra_state_attributes | { "options": options }
        elif "lookup" in sensor and "rule" in sensor and 0 < sensor["rule"] < 5 and (options := [s["value"] for s in sensor["lookup"]]):
            self._attr_device_class = "enum"
            self._attr_options = options
            self._attr_extra_state_attributes = self._attr_extra_state_attributes | { "options": options }
        if alt := get_attr(sensor, "alt"):
            self._attr_extra_state_attributes = self._attr_extra_state_attributes | { "Alt Name": alt }
        if description := get_attr(sensor, "description"):
            self._attr_extra_state_attributes = self._attr_extra_state_attributes | { "description": description }
        if friendly_name := get_attr(sensor, ATTR_FRIENDLY_NAME):
            self._attr_friendly_name = friendly_name
        if icon := get_attr(sensor, "icon"):
            self._attr_icon = icon

        self.attributes = sensor.get("attributes")

        self.registers = sensor.get("registers")

    def _friendly_name_internal(self) -> str | None:
        if self.platform and (name_translation_key := self._name_translation_key) and (name := self.platform.platform_translations.get(name_translation_key)):
            return f"{self.coordinator.inverter.name} {self._substitute_name_placeholders(name)}"
        return super()._friendly_name_internal() if not hasattr(self, "_attr_friendly_name") else f"{self.coordinator.inverter.name} {self._attr_friendly_name}"

class SolarmanWritableEntity(SolarmanEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(coordinator, sensor)

        if not "control" in sensor:
            self._attr_entity_category = EntityCategory.CONFIG

        self.code = get_code(sensor, "write", CODE.WRITE_MULTIPLE_HOLDING_REGISTERS)
        self.register = min(self.registers) if len(self.registers) > 0 else None

    async def write(self, value, state = None) -> None:
        if isinstance(value, int):
            if value > 0xFFFF:
                value = list(split_p16b(value))
            if len(self.registers) > 1:
                value = ensure_list(value)
        if isinstance(value, list):
            while len(self.registers) > len(value):
                value.insert(0, 0)
        if await self.coordinator.inverter.call(self.code, self.register, value, ACTION_ATTEMPTS_MAX) > 0 and state:
            self.set_state(state)
            self.async_write_ha_state()