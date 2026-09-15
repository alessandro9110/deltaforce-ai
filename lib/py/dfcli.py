"""Helper CLI called by install.sh and, through .deltaforce/bin/df, by the PM and the DevOps Engineer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deltaforce import backlog, databricks_io, doctor, generate  # noqa: E402
from deltaforce import config as cfg  # noqa: E402
from deltaforce.paths import ProjectPaths  # noqa: E402


def _paths(args: argparse.Namespace) -> ProjectPaths:
    if not args.target:
        raise cfg.ConfigError("--target is required for this command")
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


def cmd_event(args: argparse.Namespace) -> int:
    try:
        data = json.loads(args.data) if args.data else {}
    except json.JSONDecodeError as exc:
        raise cfg.ConfigError(f"--data is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise cfg.ConfigError("--data must be a JSON object")
    event = backlog.append_event(_paths(args), args.type, args.role, args.feature, args.task, data)
    print(json.dumps(event, ensure_ascii=False))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    try:
        items = json.loads(args.events)
    except json.JSONDecodeError as exc:
        raise cfg.ConfigError(f"events are not valid JSON: {exc.msg}") from exc
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items:
        raise cfg.ConfigError("events must be a JSON array of objects")
    for event in backlog.append_events(_paths(args), items):
        print(json.dumps(event, ensure_ascii=False))
    return cmd_validate(args)


def cmd_validate(args: argparse.Namespace) -> int:
    problems = backlog.validate_project(_paths(args))
    for problem in problems:
        print(f"✗ {problem}")
    if not problems:
        print("✓ config, conventions, state, backlog and events are valid")
    return 1 if problems else 0


def cmd_monitor(args: argparse.Namespace) -> int:
    paths = _paths(args)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from monitor import launcher

    if args.stop:
        print("monitor stopped" if launcher.stop(paths.root) else "monitor not running")
        return 0
    if not paths.venv_python.exists():
        raise cfg.ConfigError("the DeltaForce runtime is missing — re-run the installer")
    url = launcher.start(paths.root, paths.venv_python)
    if not url:
        raise cfg.ConfigError(f"the monitor did not start — see {launcher.log_file(paths.root)}")
    print(url)
    if not args.no_open:
        launcher.open_browser(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="df", description=__doc__)
    parser.add_argument("--target", help="target repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        command = sub.add_parser(name, help=help_text)
        command.set_defaults(func=func)
        # Accepted after the subcommand too; SUPPRESS keeps the global value when omitted.
        command.add_argument("--target", default=argparse.SUPPRESS, help="target repository root")
        return command

    add("write-config", cmd_write_config, "write .deltaforce/config.yaml from DF_* variables")
    add("export-env", cmd_export_env, "print DF_* assignments from the configuration")
    add("skills", cmd_skills, "print the Databricks skills of the enabled roles")
    add("roles", cmd_roles, "print the role catalog")
    add("list", cmd_list, "turn Databricks CLI JSON into menu lines").add_argument(
        "--kind", required=True, choices=sorted(databricks_io.LISTINGS)
    )
    sp = add("write-sp-profile", cmd_write_sp_profile, "write a service principal CLI profile")
    sp.add_argument("--file", required=True)
    sp.add_argument("--profile", required=True)
    sp.add_argument("--host", required=True)
    add("generate", cmd_generate, "generate project files from the configuration")
    add("doctor", cmd_doctor, "run the readiness checks")
    event = add("event", cmd_event, "append a lifecycle event to .deltaforce/events.jsonl")
    event.add_argument("type", choices=backlog.event_types())
    event.add_argument("--role", required=True)
    event.add_argument("--feature")
    event.add_argument("--task")
    event.add_argument("--data", help="JSON object")
    add("events", cmd_events, "append the lifecycle events of one change, then validate the project").add_argument(
        "events", help='JSON array, e.g. [{"type": "task_status_changed", "role": "pm", "feature": "F-001", "task": "T-001.1", "data": {}}]'
    )
    add("validate", cmd_validate, "validate config, conventions, state, backlog and events")
    monitor = add("monitor", cmd_monitor, "start the monitor and open it in the browser")
    monitor.add_argument("--no-open", action="store_true", help="print the address without opening the browser")
    monitor.add_argument("--stop", action="store_true", help="stop the running monitor")

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except cfg.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
