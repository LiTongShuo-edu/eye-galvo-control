import argparse
import os
from pathlib import Path

from .calibration import run_calibration
from .instrument import scan_resources
from .tracking import run_tracking


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Eye tracking and galvo control experiment")
    subparsers = parser.add_subparsers(dest="command", required=True)

    track = subparsers.add_parser("track", help="Run visual tracking without instrument output")
    track.add_argument("--model", type=Path, default=Path("face_landmarker.task"))

    link = subparsers.add_parser("link", help="Run visual tracking with DP832 output")
    link.add_argument("--model", type=Path, default=Path("face_landmarker.task"))
    link.add_argument("--resource", default=os.getenv("DP832_RESOURCE"))

    subparsers.add_parser("scan", help="List VISA resources")

    calibrate = subparsers.add_parser("calibrate", help="Run nine-point hardware calibration")
    calibrate.add_argument("--resource", default=os.getenv("DP832_RESOURCE"))
    calibrate.add_argument("--output", type=Path, default=Path("calibration-output.json"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "track":
        run_tracking(model_path=args.model)
    elif args.command == "link":
        run_tracking(model_path=args.model, linked=True, resource=args.resource)
    elif args.command == "scan":
        resources = scan_resources()
        print("\n".join(resources) if resources else "No VISA resources found.")
    elif args.command == "calibrate":
        if not args.resource:
            raise SystemExit("Provide --resource or set DP832_RESOURCE.")
        run_calibration(args.resource, args.output)

