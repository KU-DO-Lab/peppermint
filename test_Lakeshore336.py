from __future__ import annotations

import logging
import time
import warnings
from contextlib import suppress
from functools import wraps
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import pytest
from typing_extensions import ParamSpec

from qcodes.instrument import InstrumentBase
from qcodes.instrument_drivers.Lakeshore.lakeshore_base import (
    LakeshoreBaseSensorChannel,
)
from qcodes.instrument_drivers.Lakeshore.Model_372 import Model_372
from qcodes.logger import get_instrument_logger
from qcodes.utils import QCoDeSDeprecationWarning

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

VISA_LOGGER = ".".join((InstrumentBase.__module__, "com", "visa"))

P = ParamSpec("P")
T = TypeVar("T")


from qcodes.instrument import InstrumentBase
from Lakeshore_336 import LakeshoreModel336

class DictClass:
    def __init__(self, **kwargs):
        # https://stackoverflow.com/questions/16237659/python-how-to-implement-getattr
        super().__setattr__("_attrs", kwargs)

        for kwarg, value in kwargs.items():
            self._attrs[kwarg] = value

    def __getattr__(self, attr):
        try:
            return self._attrs[attr]
        except KeyError as e:
            raise AttributeError from e

    def __setattr__(self, name: str, value: Any) -> None:
        self._attrs[name] = value

class MockVisaInstrument:
    """
    Mixin class that overrides write_raw and ask_raw to simulate an
    instrument.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.visa_log = get_instrument_logger(self, VISA_LOGGER)  # type: ignore[arg-type]

        # This base class mixin holds two dictionaries associated with the
        # pyvisa_instrument.write()
        self.cmds: dict[str, Callable[..., Any]] = {}
        # and pyvisa_instrument.query() functions
        self.queries: dict[str, Callable[..., Any]] = {}
        # the keys are the issued VISA commands like '*IDN?' or '*OPC'
        # the values are the corresponding methods to be called on the mock
        # instrument.

        # To facilitate the definition there are the decorators `@query' and
        # `@command`. These attach an attribute to the method, so that the
        # dictionaries can be filled here in the constructor. (This is
        # borderline abusive, but makes a it easy to define mocks)
        func_names = dir(self)
        # cycle through all methods
        for func_name in func_names:
            with warnings.catch_warnings():
                if func_name == "_name":
                    # silence warning when getting deprecated attribute
                    warnings.simplefilter("ignore", category=QCoDeSDeprecationWarning)

                f = getattr(self, func_name)
                # only add for methods that have such an attribute
                with suppress(AttributeError):
                    self.queries[getattr(f, "query_name")] = f
                with suppress(AttributeError):
                    self.cmds[getattr(f, "command_name")] = f

    def write_raw(self, cmd) -> None:
        cmd_parts = cmd.split(" ")
        cmd_str = cmd_parts[0].upper()
        if cmd_str in self.cmds:
            args = "".join(cmd_parts[1:])
            self.visa_log.debug(f"Query: {cmd} for command {cmd_str} with args {args}")
            self.cmds[cmd_str](args)
        else:
            super().write_raw(cmd)  # type: ignore[misc]

    def ask_raw(self, cmd) -> Any:
        query_parts = cmd.split(" ")
        query_str = query_parts[0].upper()
        if query_str in self.queries:
            args = "".join(query_parts[1:])
            self.visa_log.debug(
                f"Query: {cmd} for command {query_str} with args {args}"
            )
            response = self.queries[query_str](args)
            self.visa_log.debug(f"Response: {response}")
            return response
        else:
            return super().ask_raw(cmd)  # type: ignore[misc]

def instrument_fixture(
    scope: Literal["session"]
    | Literal["package"]
    | Literal["module"]
    | Literal["class"]
    | Literal["function"] = "function",
    name=None,
):
    def wrapper(func):
        @pytest.fixture(scope=scope, name=name)
        def wrapped_fixture():
            inst = func()
            try:
                yield inst
            finally:
                inst.close()

        return wrapped_fixture

    return wrapper

def query(name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def wrapper(func: Callable[P, T]) -> Callable[P, T]:
        func.query_name = name.upper()  # type: ignore[attr-defined]
        return func

    return wrapper

def split_args(split_char: str = ","):
    def wrapper(func):
        @wraps(func)
        def decorated_func(self, string_arg):
            args = string_arg.split(split_char)
            return func(self, *args)

        return decorated_func

    return wrapper

log = logging.getLogger(__name__)

VISA_LOGGER = ".".join((InstrumentBase.__module__, "com", "visa"))

def command(name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def wrapper(func: Callable[P, T]) -> Callable[P, T]:
        func.command_name = name.upper()  # type: ignore[attr-defined]
        return func

    return wrapper

class LakeshoreModel336Mock(MockVisaInstrument, LakeshoreModel336):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # initial values
        self.heaters: dict[str, DictClass] = {}
        self.heaters["1"] = DictClass(
            P=1,
            I=2,
            D=3,
            mode=1,  # 'off'
            input_channel=1,  # 'A'
            powerup_enable=0,
            polarity=0,
            use_filter=0,
            delay=1,
            output_range=0,
            setpoint=4,
        )
        self.heaters["2"] = DictClass(
            P=1,
            I=2,
            D=3,
            mode=2,  # 'closed_loop'
            input_channel=2,  # 'B'
            powerup_enable=0,
            polarity=0,
            use_filter=0,
            delay=1,
            output_range=0,
            setpoint=4,
        )
        self.heaters["3"] = DictClass(
            mode=4,  # 'monitor_out'
            input_channel=2,  # 'B'
            powerup_enable=0,
            polarity=0,
            use_filter=0,
            delay=1,
            output_range=0,
            setpoint=4,
        )
        self.heaters["4"] = DictClass(
            mode=5,  # 'warm_up'
            input_channel=1,  # 'A'
            powerup_enable=0,
            polarity=0,
            use_filter=0,
            delay=1,
            output_range=0,
            setpoint=4,
        )

        self.channel_mock = {
            str(i): DictClass(
                t_limit=i,
                T=4,
                sensor_name=f"sensor_{i}",
                sensor_type=1,  # 'diode',
                auto_range_enabled=0,  # 'off',
                range=0,
                compensation_enabled=0,  # False,
                units=1,  # 'kelvin'
            )
            for i in self.channel_name_command.keys()
        }

        # simulate delayed heating
        self.simulate_heating = False
        self.start_heating_time = time.perf_counter()

    def start_heating(self):
        self.start_heating_time = time.perf_counter()
        self.simulate_heating = True

    def get_t_when_heating(self):
        """
        Simply define a fixed setpoint of 4 k for now
        """
        delta = abs(time.perf_counter() - self.start_heating_time)
        # make it simple to start with: linear ramp 1K per second
        # start at 7K.
        return max(4, 7 - delta)

    @query("PID?")
    def pidq(self, arg):
        heater = self.heaters[arg]
        return f"{heater.P},{heater.I},{heater.D}"

    @command("PID")
    @split_args()
    def pid(self, output, P, I, D):  # noqa  E741
        for a, v in zip(["P", "I", "D"], [P, I, D]):
            setattr(self.heaters[output], a, v)

    @query("OUTMODE?")
    def outmodeq(self, arg):
        heater = self.heaters[arg]
        return f"{heater.mode},{heater.input_channel},{heater.powerup_enable}"

    @command("OUTMODE")
    @split_args()
    def outputmode(self, output, mode, input_channel, powerup_enable):
        h = self.heaters[output]
        h.output = output
        h.mode = mode
        h.input_channel = input_channel
        h.powerup_enable = powerup_enable

    @query("INTYPE?")
    def intypeq(self, channel):
        ch = self.channel_mock[channel]
        return (
            f"{ch.sensor_type},"
            f"{ch.auto_range_enabled},{ch.range},"
            f"{ch.compensation_enabled},{ch.units}"
        )

    @command("INTYPE")
    @split_args()
    def intype(
        self,
        channel,
        sensor_type,
        auto_range_enabled,
        range_,
        compensation_enabled,
        units,
    ):
        ch = self.channel_mock[channel]
        ch.sensor_type = sensor_type
        ch.auto_range_enabled = auto_range_enabled
        ch.range = range_
        ch.compensation_enabled = compensation_enabled
        ch.units = units

    @query("RANGE?")
    def rangeq(self, heater):
        h = self.heaters[heater]
        return f"{h.output_range}"

    @command("RANGE")
    @split_args()
    def range_cmd(self, heater, output_range):
        h = self.heaters[heater]
        h.output_range = output_range

    @query("SETP?")
    def setpointq(self, heater):
        h = self.heaters[heater]
        return f"{h.setpoint}"

    @command("SETP")
    @split_args()
    def setpoint(self, heater, setpoint):
        h = self.heaters[heater]
        h.setpoint = setpoint

    @query("TLIMIT?")
    def tlimitq(self, channel):
        chan = self.channel_mock[channel]
        return f"{chan.tlimit}"

    @command("TLIMIT")
    @split_args()
    def tlimitcmd(self, channel, tlimit):
        chan = self.channel_mock[channel]
        chan.tlimit = tlimit

    @query("KRDG?")
    def temperature(self, output):
        chan = self.channel_mock[output]
        if self.simulate_heating:
            return self.get_t_when_heating()
        return f"{chan.T}"


@instrument_fixture(scope="function", name="lakeshore_336")
def _make_lakeshore_336():
    return LakeshoreModel336Mock(
        "lakeshore_336_fixture",
        "GPIB::2::INSTR",
        pyvisa_sim_file="lakeshore_model336.yaml",
        device_clear=False,
    )


def test_pid_set(lakeshore_336) -> None:
    ls = lakeshore_336
    P, I, D = 1, 2, 3  # noqa  E741
    # Only current source outputs/heaters have PID parameters,
    # voltages source outputs/heaters do not.
    outputs = [ls.output_1, ls.output_2]
    for h in outputs:  # a.k.a. heaters
        h.P(P)
        h.I(I)
        h.D(D)
        assert (h.P(), h.I(), h.D()) == (P, I, D)


def test_output_mode(lakeshore_336) -> None:
    ls = lakeshore_336
    mode = "off"
    input_channel = "A"
    powerup_enable = True
    outputs = [getattr(ls, f"output_{n}") for n in range(1, 5)]
    for h in outputs:  # a.k.a. heaters
        h.mode(mode)
        h.input_channel(input_channel)
        h.powerup_enable(powerup_enable)
        assert h.mode() == mode
        assert h.input_channel() == input_channel
        assert h.powerup_enable() == powerup_enable


def test_range(lakeshore_336) -> None:
    ls = lakeshore_336
    output_range = "medium"
    outputs = [getattr(ls, f"output_{n}") for n in range(1, 5)]
    for h in outputs:  # a.k.a. heaters
        h.output_range(output_range)
        assert h.output_range() == output_range


def test_tlimit(lakeshore_336) -> None:
    ls = lakeshore_336
    tlimit = 5.1
    for ch in ls.channels:
        ch.t_limit(tlimit)
        assert ch.t_limit() == tlimit


def test_setpoint(lakeshore_336) -> None:
    ls = lakeshore_336
    setpoint = 5.1
    outputs = [getattr(ls, f"output_{n}") for n in range(1, 5)]
    for h in outputs:  # a.k.a. heaters
        h.setpoint(setpoint)
        assert h.setpoint() == setpoint


def test_curve_parameters(lakeshore_336) -> None:
    # The curve numbers are assigned in the simulation pyvisa sim
    # YAML file for each sensor/channel, and properties of the
    # curves also include curve number in them to help testing
    for ch, curve_number in zip(lakeshore_336.channels, (42, 41, 40, 39)):
        assert ch.curve_number() == curve_number
        assert ch.curve_name().endswith(str(curve_number))
        assert ch.curve_sn().endswith(str(curve_number))
        assert ch.curve_format() == "V/K"
        assert str(int(ch.curve_limit())).endswith(str(curve_number))
        assert ch.curve_coefficient() == "negative"


def test_select_range_limits(lakeshore_336) -> None:
    h = lakeshore_336.output_1
    ranges = [1, 2, 3]
    h.range_limits(ranges)

    for i in ranges:
        h.set_range_from_temperature(i - 0.5)
        assert h.output_range() == h.INVERSE_RANGES[i]

    i = 3
    h.set_range_from_temperature(i + 0.5)
    assert h.output_range() == h.INVERSE_RANGES[len(ranges)]


def test_set_and_wait_unit_setpoint_reached(lakeshore_336) -> None:
    ls = lakeshore_336
    ls.output_1.setpoint(4)
    ls.start_heating()
    ls.output_1.wait_until_set_point_reached()


def test_blocking_t(lakeshore_336) -> None:
    ls = lakeshore_336
    h = ls.output_1
    ranges = [1.2, 2.4, 3.1]
    h.range_limits(ranges)
    ls.start_heating()
    h.blocking_t(4)
