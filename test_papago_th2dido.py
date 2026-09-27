"""Behavior tests using small Checkmk API doubles (no running site required)."""
import enum
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class State(enum.IntEnum):
    OK = 0
    WARN = 1
    CRIT = 2
    UNKNOWN = 3


class Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Metric:
    def __init__(self, name, value):
        self.name, self.value = name, value


api = types.ModuleType("cmk.agent_based.v2")
for name in ("CheckPlugin", "Result", "Service", "SimpleSNMPSection", "SNMPTree"):
    setattr(api, name, Record)
api.State, api.Metric, api.OIDEnd, api.StringTable = State, Metric, object, list
api.exists = lambda oid: ("exists", oid)
api.all_of = lambda *args: args
api.get_value_store = dict
humidity = types.ModuleType("cmk.plugins.lib.humidity")
humidity.check_humidity = Mock(return_value=[])
temperature = types.ModuleType("cmk.plugins.lib.temperature")
temperature.check_temperature = Mock(return_value=[])
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "papago_under_test", ROOT / "cmk_addons_plugins/papouch/agent_based/papouch_papago_th2dido.py"
)
plugin = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    "cmk.agent_based.v2": api,
    "cmk.plugins.lib.humidity": humidity,
    "cmk.plugins.lib.temperature": temperature,
    spec.name: plugin,
}):
    spec.loader.exec_module(plugin)


class PapagoTests(unittest.TestCase):
    def setUp(self):
        temperature.check_temperature.reset_mock()
        humidity.check_humidity.reset_mock()

    def test_sensor_discovery_and_scaling(self):
        section = plugin.parse_sensors([
            ["1", "1", "0", "-123", "0"],
            ["2", "2", "0", "456", "0"],
            ["3", "3", "0", "-200", "0"],
            ["4", "0", "4", "0", "0"],
        ])
        self.assertEqual(len(section), 3)
        self.assertEqual(section["1"].reading, -12.3)
        self.assertEqual(section["2"].reading, 45.6)
        for kind in (1, 2, 3):
            self.assertEqual([s.item for s in plugin.discover_sensors(section, kind=kind)], [str(kind)])

    def test_all_device_statuses(self):
        for status, expected in ((0, State.OK), (1, State.UNKNOWN), (2, State.WARN),
                                 (3, State.WARN), (4, State.CRIT), (99, State.UNKNOWN)):
            with self.subTest(status=status):
                sensor = plugin.Sensor(1, status, 22.5, 0)
                result = list(plugin.check_temperature_sensor("1", {}, {"1": sensor}))
                if status in (0, 2, 3):
                    self.assertEqual(temperature.check_temperature.call_args.kwargs["dev_status"], expected)
                else:
                    self.assertEqual(result[0].state, expected)
                    temperature.check_temperature.assert_not_called()
                temperature.check_temperature.reset_mock()

    def test_temperature_unit_conversion(self):
        for raw, unit, expected in (("250", "0", 25), ("770", "1", 25), ("2982", "2", 25.05)):
            section = plugin.parse_sensors([["1", "1", "0", raw, unit]])
            list(plugin.check_temperature_sensor("1", {}, section))
            self.assertAlmostEqual(temperature.check_temperature.call_args.kwargs["reading"], expected)

    def test_unknown_temperature_unit(self):
        result = list(plugin.check_temperature_sensor("1", {}, {"1": plugin.Sensor(1, 0, 20, 8)}))
        self.assertEqual(result[0].state, State.UNKNOWN)
        temperature.check_temperature.assert_not_called()

    def test_humidity_valid_units_and_threshold_parameters(self):
        params = {"levels": (60., 80.)}
        for unit in (0, 3):
            list(plugin.check_humidity_sensor("2", params, {"2": plugin.Sensor(2, 2, 85., unit)}))
            humidity.check_humidity.assert_called_with(humidity=85., params=params)

    def test_invalid_humidity_never_emits_measurements(self):
        for status, unit in ((1, 0), (4, 0), (99, 0), (0, 8)):
            result = list(plugin.check_humidity_sensor("2", {}, {"2": plugin.Sensor(2, status, 0, unit)}))
            self.assertIn(result[-1].state, (State.UNKNOWN, State.CRIT))
            humidity.check_humidity.assert_not_called()

    def test_input_counter_scaling_and_states(self):
        section = plugin.parse_inputs([
            ["1", "0", "49", "3", " kWh "], ["2", "1", "4294967295", "0", ""],
        ])
        self.assertEqual([s.item for s in plugin.discover_io(section)], ["1", "2"])
        first = list(plugin.check_input("1", section))
        self.assertEqual(first[0].summary, "State: OFF")
        self.assertEqual(first[1].summary, "Counter: 0.049 kWh")
        self.assertEqual(first[2].value, 0.049)
        second = list(plugin.check_input("2", section))
        self.assertEqual(second[0].summary, "State: ON")
        self.assertEqual(second[2].value, 4294967295)

    def test_relay_off_on_and_unknown(self):
        for value, state in ((0, State.OK), (1, State.OK), (2, State.UNKNOWN)):
            section = plugin.parse_outputs([["1", str(value)]])
            self.assertEqual(list(plugin.check_output("1", section))[0].state, state)

    def test_missing_channels_and_empty_tables(self):
        for parse in (plugin.parse_inputs, plugin.parse_outputs, plugin.parse_sensors):
            self.assertEqual(parse([]), {})
        self.assertEqual(list(plugin.check_input("1", {})), [])
        self.assertEqual(list(plugin.check_output("1", {})), [])
        self.assertEqual(list(plugin.check_temperature_sensor("1", {}, {})), [])
        self.assertEqual(list(plugin.check_humidity_sensor("2", {}, {})), [])

    def test_model_specific_fetch_and_detection(self):
        self.assertEqual(plugin.DETECT, (
            ("exists", ".1.3.6.1.4.1.18248.34.1.2.1.1.1.1"),
            ("exists", ".1.3.6.1.4.1.18248.34.1.3.1.1.1.1"),
        ))
        self.assertEqual(plugin.snmp_section_papouch_papago_th2dido.fetch.base,
                         ".1.3.6.1.4.1.18248.34.1.4.1.1")


if __name__ == "__main__":
    unittest.main()
