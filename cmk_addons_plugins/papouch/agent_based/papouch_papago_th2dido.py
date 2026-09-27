#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""PAPAGO TH 2DI DO ETH, Checkmk Check API v2.

OIDs and encodings: Papouch PAPAGO TH 2DI DO manual, SNMP section.
Separate from the 2TH plugin because this model uses enterprise subtree 34.
"""

from dataclasses import dataclass

from cmk.agent_based.v2 import (
    CheckPlugin, Metric, OIDEnd, Result, Service, SimpleSNMPSection,
    SNMPTree, State, StringTable, all_of, exists, get_value_store,
)
from cmk.plugins.lib.humidity import check_humidity
from cmk.plugins.lib.temperature import check_temperature


BASE = ".1.3.6.1.4.1.18248.34.1"
# Use the model-specific tree instead of guessing firmware sysDescr spellings
# or relying on the malformed sysObjectID used by some older Papago firmware.
DETECT = all_of(
    exists(BASE + ".2.1.1.1.1"),
    exists(BASE + ".3.1.1.1.1"),
)
SENSOR_NAMES = {1: "Temperature", 2: "Humidity", 3: "Dew point"}
SENSOR_STATES = {
    0: (State.OK, "Within device limits"),
    1: (State.UNKNOWN, "Not yet measured"),
    2: (State.WARN, "Above device upper limit"),
    3: (State.WARN, "Below device lower limit"),
    4: (State.CRIT, "Measurement error"),
}


@dataclass(frozen=True)
class Sensor:
    kind: int
    status: int
    reading: float
    unit: int


def parse_sensors(string_table: StringTable) -> dict[str, Sensor]:
    section = {}
    for index, kind, status, reading, unit in string_table:
        # This model has one sensor connector with three measured quantities.
        if int(kind) in SENSOR_NAMES:
            section[index] = Sensor(int(kind), int(status), float(reading) / 10, int(unit))
    return section


snmp_section_papouch_papago_th2dido = SimpleSNMPSection(
    name="papouch_papago_th2dido",
    detect=DETECT,
    fetch=SNMPTree(base=BASE + ".4.1.1", oids=[OIDEnd(), "1", "2", "3", "4"]),
    parse_function=parse_sensors,
)


def discover_sensors(section, *, kind):
    for index, sensor in section.items():
        if sensor.kind == kind:
            yield Service(item=index)


def discover_temperature(section):
    yield from discover_sensors(section, kind=1)


def discover_humidity(section):
    yield from discover_sensors(section, kind=2)


def discover_dewpoint(section):
    yield from discover_sensors(section, kind=3)


def sensor_status(sensor):
    return SENSOR_STATES.get(sensor.status, (State.UNKNOWN, f"Unknown sensor status: {sensor.status}"))


def check_temperature_sensor(item, params, section):
    sensor = section.get(item)
    if sensor is None:
        return
    state, label = sensor_status(sensor)
    if sensor.status not in (0, 2, 3):
        # Invalid/stale readings must not produce plausible measurement graphs.
        yield Result(state=state, summary=label)
        return
    if sensor.unit not in (0, 1, 2):
        yield Result(state=State.UNKNOWN, summary=f"Unknown temperature unit: {sensor.unit}")
        return
    reading = sensor.reading
    if sensor.unit == 1:
        reading = (reading - 32) * 5 / 9
    elif sensor.unit == 2:
        reading -= 273.15
    yield from check_temperature(
        reading=reading, params=params, unique_name=f"papago_th2dido_{item}",
        value_store=get_value_store(), dev_unit="c", dev_status=state,
        dev_status_name=label,
    )


def check_humidity_sensor(item, params, section):
    sensor = section.get(item)
    if sensor is None:
        return
    state, label = sensor_status(sensor)
    yield Result(state=state, summary=label)
    if sensor.status not in (0, 2, 3):
        return
    # The manual lists both per-variable code 0 and legacy SNMP code 3 for %.
    if sensor.unit not in (0, 3):
        yield Result(state=State.UNKNOWN, summary=f"Unknown humidity unit: {sensor.unit}")
        return
    yield from check_humidity(humidity=sensor.reading, params=params)


check_plugin_papouch_papago_th2dido_temperature = CheckPlugin(
    name="papouch_papago_th2dido_temperature", sections=["papouch_papago_th2dido"],
    service_name="Temperature %s", discovery_function=discover_temperature,
    check_function=check_temperature_sensor, check_ruleset_name="temperature",
    check_default_parameters={},
)
check_plugin_papouch_papago_th2dido_humidity = CheckPlugin(
    name="papouch_papago_th2dido_humidity", sections=["papouch_papago_th2dido"],
    service_name="Humidity %s", discovery_function=discover_humidity,
    check_function=check_humidity_sensor, check_ruleset_name="humidity",
    check_default_parameters={"levels": (60.0, 80.0), "levels_lower": (30.0, 20.0)},
)
check_plugin_papouch_papago_th2dido_dewpoint = CheckPlugin(
    name="papouch_papago_th2dido_dewpoint", sections=["papouch_papago_th2dido"],
    service_name="Dew point %s", discovery_function=discover_dewpoint,
    check_function=check_temperature_sensor, check_ruleset_name="temperature",
    check_default_parameters={},
)


@dataclass(frozen=True)
class DigitalInput:
    state: int
    counter: float
    unit: str


def parse_inputs(string_table: StringTable) -> dict[str, DigitalInput]:
    return {
        index: DigitalInput(int(state), int(counter) / 10 ** int(decimals), unit.strip())
        for index, state, counter, decimals, unit in string_table
    }


def parse_outputs(string_table: StringTable) -> dict[str, int]:
    return {index: int(state) for index, state in string_table}


snmp_section_papouch_papago_th2dido_inputs = SimpleSNMPSection(
    name="papouch_papago_th2dido_inputs", detect=DETECT,
    fetch=SNMPTree(base=BASE + ".2.1.1", oids=[OIDEnd(), "1", "2", "3", "4"]),
    parse_function=parse_inputs,
)
snmp_section_papouch_papago_th2dido_outputs = SimpleSNMPSection(
    name="papouch_papago_th2dido_outputs", detect=DETECT,
    fetch=SNMPTree(base=BASE + ".3.1.1", oids=[OIDEnd(), "1"]),
    parse_function=parse_outputs,
)


def discover_io(section):
    for index in section:
        yield Service(item=index)


def digital_result(state):
    if state not in (0, 1):
        return Result(state=State.UNKNOWN, summary=f"Unknown digital state: {state}")
    # Neither electrical state is inherently a fault; show both as informational.
    return Result(state=State.OK, summary="State: ON" if state else "State: OFF")


def check_input(item, section):
    channel = section.get(item)
    if channel is None:
        return
    yield digital_result(channel.state)
    yield Result(state=State.OK, summary=f"Counter: {channel.counter:g} {channel.unit}".rstrip())
    yield Metric("papago_counter", channel.counter)


def check_output(item, section):
    if item in section:
        yield digital_result(section[item])


check_plugin_papouch_papago_th2dido_inputs = CheckPlugin(
    name="papouch_papago_th2dido_inputs", service_name="Digital input %s",
    discovery_function=discover_io, check_function=check_input,
)
check_plugin_papouch_papago_th2dido_outputs = CheckPlugin(
    name="papouch_papago_th2dido_outputs", service_name="Relay output %s",
    discovery_function=discover_io, check_function=check_output,
)
