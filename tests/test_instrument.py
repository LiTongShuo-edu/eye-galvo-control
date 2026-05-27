from eye_galvo.instrument import GalvoController


class FakeSession:
    timeout = 0

    def __init__(self):
        self.commands: list[str] = []
        self.closed = False

    def query(self, command: str) -> str:
        self.commands.append(command)
        return "RIGOL,DP832,DEMO"

    def write(self, command: str) -> None:
        self.commands.append(command)

    def close(self) -> None:
        self.closed = True


def test_controller_applies_voltage_and_safe_shutdown_sequence():
    session = FakeSession()

    with GalvoController(session) as controller:
        assert controller.enable() == "RIGOL,DP832,DEMO"
        assert controller.update_angles(4.5, -4.5)
        assert not controller.update_angles(4.5, -4.5)

    assert ":SOUR1:VOLT 6.000" in session.commands
    assert ":SOUR2:VOLT 4.000" in session.commands
    assert session.commands[-5:] == [
        ":SOUR1:VOLT 5.000",
        ":SOUR2:VOLT 5.000",
        ":OUTP CH1,OFF",
        ":OUTP CH2,OFF",
        ":OUTP CH3,OFF",
    ]
    assert session.closed

