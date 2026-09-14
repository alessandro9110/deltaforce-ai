"""Helper CLI called by install.sh through the project-local uv and Python."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deltaforce import config as cfg  # noqa: E402
from deltaforce import databricks_io, doctor, generate  # noqa: E402
from deltaforce.paths import ProjectPaths  # noqa: E402


def _paths(args: argparse.Namespace) -> ProjectPaths:
    return ProjectPaths(Path(args.target).resolve())


def cmd_write_config(args: argparse.Namespace) -> int:
    paths = _paths(args)
    data = cfg.build_from_env(os.environ)
    cfg.validate(data)
    cfg.write_config(paths.config, data)
    return 0


def cmd_export_env(args: argparse.Namespace) -> int:
    sys.stdout.write(cfg.export_env(cfg.load_config(_paths(args).config)))
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    data = cfg.load_config(_paths(args).config)
    print(",".join(cfg.skills_for_roles(data["team"]["roles"])))
    return 0


def cmd_roles(_: argparse.Namespace) -> int:
    for name, spec in cfg.load_roles().items():
        print(f"{name}|{spec['title']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for value, label in databricks_io.parse_listing(args.kind, sys.stdin.read()):
        print(f"{value}|{label}")
    return 0


def cmd_write_sp_profile(args: argparse.Namespace) -> int:
    databricks_io.write_profile(
        Path(args.file),
        args.profile,
        {
            "host": args.host,
            "client_id": os.environ["DF_SP_CLIENT_ID"],
            "client_secret": os.environ["DF_SP_CLIENT_SECRET"],
        },
    )
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    paths = _paths(args)
    for written in generate.generate_all(cfg.load_config(paths.config), paths):
        print(written)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor.run(_paths(args))
    doctor.print_report(report)
    return 0 if report["ready"] else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="dfcli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, needs_target: bool = True) -> argparse.ArgumentParser:
        command = sub.add_parser(name)
        command.set_defaults(func=func)
        if needs_target:
            command.add_argument("--target", required=True, help="target repository root")
        return command

    add("write-config", cmd_write_config)
    add("export-env", cmd_export_env)
    add("skills", cmd_skills)
    add("roles", cmd_roles, needs_target=False)
    add("list", cmd_list, needs_target=False).add_argument(
        "--kind", required=True, choices=sorted(databricks_io.LISTINGS)
    )
    sp = add("write-sp-profile", cmd_write_sp_profile, needs_target=False)
    sp.add_argument("--file", required=True)
    sp.add_argument("--profile", required=True)
    sp.add_argument("--host", required=True)
    add("generate", cmd_generate)
    add("doctor", cmd_doctor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except cfg.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
