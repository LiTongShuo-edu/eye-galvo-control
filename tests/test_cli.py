from pathlib import Path

from eye_galvo.cli import build_parser


def test_calibrate_defaults_to_loaded_calibration_filename():
    args = build_parser().parse_args(["calibrate", "--resource", "USB::DEMO"])

    assert args.output == Path("galvo_calibration.json")
