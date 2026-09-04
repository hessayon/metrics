import json
import sys
import typing


def write_reports(reports: list[dict[str, typing.Any]]) -> None:
    json.dump(reports, sys.stdout, indent=2)
    sys.stdout.write("\n")
