from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from ..slash_command_install import (
    install_slash_commands,
    render_slash_command_install_markdown,
)
from ..slash_commands import build_slash_command_catalog, render_slash_command_catalog_markdown


PrintPayload = Callable[
    [dict[str, object], str, Callable[[dict[str, object]], str]],
    None,
]
FormatSelector = Callable[..., str]


def register_slash_commands_command(
    subparsers: argparse._SubParsersAction,
    add_subcommand_format: Callable[[argparse.ArgumentParser], None],
) -> None:
    parser = subparsers.add_parser(
        "slash-commands",
        help="List LoopX chat slash commands, onboarding hints, and CLI references.",
    )
    add_subcommand_format(parser)
    parser.add_argument(
        "--cli-bin",
        default="loopx",
        help="LoopX CLI binary name to show in command references.",
    )
    parser.add_argument(
        "--no-legacy-aliases",
        action="store_true",
        help="Hide legacy /loop-global-* aliases from the command catalog.",
    )
    install_group = parser.add_mutually_exclusive_group()
    install_group.add_argument(
        "--install",
        action="store_true",
        help="Install LoopX command skill files for supported hosts.",
    )
    install_group.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove LoopX-managed command skill files for supported hosts while preserving user-owned files.",
    )
    parser.add_argument(
        "--surface",
        action="append",
        choices=[
            "all",
            "codex",
            "codex-cli",
            "codex-app",
            "codex-app-ssh",
            "codex-ide-plugin",
            "codex-ide",
            "claude-code",
            "opencode",
            "gemini",
            "gemini-cli",
            "cursor",
            "cursor-agent",
            "zcode",
            "z-code",
            "agy",
            "antigravity",
            "kiro",
            "kiro-cli",
            "devin",
            "devin-cli",
            "pi",
        ],
        help=(
            "Host surface to install. Repeatable. Defaults to static command facades "
            "for Codex, Claude Code, and OpenCode. `gemini`, `cursor`, `zcode`, "
            "`agy`, `kiro-cli`, `devin-cli`, `pi` are opt-in: they write into those hosts' own "
            "homes only when requested."
        ),
    )
    parser.add_argument(
        "--with-goal-bridge",
        action="store_true",
        help=(
            "Also install or uninstall the executable OpenCode goal bridge. Requires "
            "an effective OpenCode surface and explicit opt-in."
        ),
    )
    parser.add_argument(
        "--codex-home",
        help="Codex home for skill installation. Defaults to CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--claude-home",
        help="Claude Code home for skill installation. Defaults to CLAUDE_HOME or ~/.claude.",
    )
    parser.add_argument(
        "--gemini-home",
        help="Gemini CLI home for skill installation. Defaults to GEMINI_HOME or ~/.gemini.",
    )
    parser.add_argument(
        "--cursor-home",
        help="Cursor CLI home for MCP registration. Defaults to CURSOR_HOME or ~/.cursor.",
    )
    parser.add_argument(
        "--zcode-home",
        dest="zcode_home",
        help="ZCode home for skill installation. Defaults to ZCODE_HOME or ~/.zcode.",
    )
    parser.add_argument(
        "--zcode-agents-home",
        dest="zcode_home",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--opencode-home",
        help="OpenCode config directory. Defaults to OPENCODE_CONFIG_DIR or ~/.config/opencode.",
    )
    parser.add_argument(
        "--pi-project",
        default=".",
        help="Project directory for the Pi goal extension install. Defaults to the current directory.",
    )
    parser.add_argument(
        "--devin-scope",
        choices=["global", "project", "agents-global", "agents-project"],
        default=None,
        help=(
            "Install scope for the Devin CLI surface. `global` writes to "
            "~/.config/devin/skills (Devin-specific, default for backward "
            "compatibility); `project` writes to .devin/skills in the project "
            "dir (Devin-specific, this project only); `agents-global` writes "
            "to ~/.agents/skills (.agents standard, cross-host); "
            "`agents-project` writes to .agents/skills in the project dir "
            "(.agents standard, this project only, cross-host). If omitted "
            "and devin-cli is in the surface list, the command prompts "
            "interactively (defaults to global in non-interactive mode)."
        ),
    )
    parser.add_argument(
        "--devin-project",
        default=".",
        help="Project directory for project-scoped Devin CLI skill install. Defaults to the current directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what slash-command files would be installed without writing them.",
    )


def _resolve_devin_scope(args: argparse.Namespace) -> str:
    """Resolve the Devin CLI install scope, prompting when unspecified.

    Returns one of ``"global"``, ``"project"``, ``"agents-global"``,
    ``"agents-project"``. When ``--devin-scope`` is set explicitly it wins.
    When it is omitted and devin-cli is in the surface list, the command
    prompts interactively; non-interactive sessions (piped stdin, tests,
    scripts) default to ``"global"`` to preserve backward compatibility.
    """
    if args.devin_scope:
        return args.devin_scope
    surfaces = args.surface or []
    has_devin = any(s in ("devin", "devin-cli") for s in surfaces)
    if not has_devin:
        return "global"
    if not sys.stdin.isatty():
        return "global"
    print(
        "Devin CLI skill install scope:\n"
        "  [1] global         - ~/.config/devin/skills (Devin-specific, all projects)\n"
        "  [2] project         - .devin/skills in the project dir (Devin-specific, this project only)\n"
        "  [3] agents-global   - ~/.agents/skills (.agents standard, cross-host, all projects)\n"
        "  [4] agents-project  - .agents/skills in the project dir (.agents standard, cross-host, this project only)",
        file=sys.stderr,
    )
    try:
        choice = input("Choose [1/2/3/4] (default 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "global"
    return {"2": "project", "3": "agents-global", "4": "agents-project"}.get(
        choice, "global"
    )


def handle_slash_commands_command(
    args: argparse.Namespace,
    *,
    output_format: FormatSelector,
    print_payload: PrintPayload,
) -> int | None:
    if args.command != "slash-commands":
        return None
    if args.install or args.uninstall or args.dry_run:
        devin_scope = _resolve_devin_scope(args)
        payload = install_slash_commands(
            execute=bool((args.install or args.uninstall) and not args.dry_run),
            uninstall=bool(args.uninstall),
            with_goal_bridge=bool(args.with_goal_bridge),
            surfaces=args.surface,
            cli_bin=args.cli_bin,
            include_legacy_aliases=not bool(args.no_legacy_aliases),
            codex_home=args.codex_home,
            claude_home=args.claude_home,
            opencode_home=args.opencode_home,
            gemini_home=args.gemini_home,
            cursor_home=args.cursor_home,
            zcode_home=getattr(args, "zcode_home", None),
            pi_project=args.pi_project,
            devin_scope=devin_scope,
            devin_project=args.devin_project,
        )
        print_payload(payload, output_format(args), render_slash_command_install_markdown)
        return 0 if payload.get("ok") is True else 1
    payload = build_slash_command_catalog(
        cli_bin=args.cli_bin,
        include_legacy_aliases=not bool(args.no_legacy_aliases),
    )
    print_payload(payload, output_format(args), render_slash_command_catalog_markdown)
    return 0
