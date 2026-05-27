from contextlib import AbstractContextManager
from typing import Protocol

from .geometry import angles_to_voltages


class InstrumentSession(Protocol):
    timeout: int

    def query(self, command: str) -> str: ...

    def write(self, command: str) -> object: ...

    def close(self) -> object: ...


class GalvoController(AbstractContextManager["GalvoController"]):
    """Apply bounded DP832 commands and always shut outputs down on exit."""

    def __init__(self, session: InstrumentSession, center_voltage: float = 5.0) -> None:
        self.session = session
        self.center_voltage = center_voltage
        self.enabled = False
        self.last_voltages: tuple[float, float] | None = None

    def enable(self) -> str:
        identity = self.session.query("*IDN?").strip()
        self.session.write(f":SOUR3:VOLT {self.center_voltage:.3f}")
        for channel in (3, 1, 2):
            self.session.write(f":OUTP CH{channel},ON")
        self.enabled = True
        return identity

    def set_voltages(self, voltage_x: float, voltage_y: float) -> None:
        if not self.enabled:
            raise RuntimeError("Enable the controller before sending voltages.")
        self.session.write(f":SOUR1:VOLT {voltage_x:.3f}")
        self.session.write(f":SOUR2:VOLT {voltage_y:.3f}")
        self.last_voltages = (voltage_x, voltage_y)

    def update_angles(self, angle_x: float, angle_y: float, deadzone: float = 0.02) -> bool:
        target = angles_to_voltages(angle_x, angle_y, center_voltage=self.center_voltage)
        if self.last_voltages is not None and max(
            abs(target[0] - self.last_voltages[0]),
            abs(target[1] - self.last_voltages[1]),
        ) <= deadzone:
            return False
        self.set_voltages(*target)
        return True

    def close(self) -> None:
        try:
            if self.enabled:
                self.session.write(f":SOUR1:VOLT {self.center_voltage:.3f}")
                self.session.write(f":SOUR2:VOLT {self.center_voltage:.3f}")
                for channel in (1, 2, 3):
                    self.session.write(f":OUTP CH{channel},OFF")
        finally:
            self.session.close()
            self.enabled = False

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def open_controller(resource: str) -> GalvoController:
    if not resource:
        raise ValueError("Provide a VISA resource with --resource or DP832_RESOURCE.")
    import pyvisa

    manager = pyvisa.ResourceManager()
    session = manager.open_resource(resource)
    session.timeout = 2000
    return GalvoController(session)


def scan_resources() -> tuple[str, ...]:
    import pyvisa

    return tuple(pyvisa.ResourceManager().list_resources())

