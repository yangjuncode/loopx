from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEVIN_CLI_INSTALL_SURFACE = "devin"
DEVIN_CLI_AGENT_TYPE = "devin-cli"
SKILLS_ROOT_LABEL = "~/.config/devin/skills"
DEVIN_CLI_ACCEPTED_INPUTS = (
    "devin-cli",
    "devin_cli",
    "devin cli",
    "devin",
)

# Native goal primitive built into the devin binary. Only what the host
# itself contracts is recorded here; the host's release notes document
# `/goal <objective>` keeping the same session working across turns until it
# reports complete or blocked, `/goal` showing status, `/goal resume`
# continuing an interrupted goal, `/goal clear` dropping it, and a run
# pausing itself after 50 turns.
DEVIN_CLI_GOAL_COMMAND = "/goal"
DEVIN_CLI_GOAL_RESUME_COMMAND = "/goal resume"
DEVIN_CLI_GOAL_CLEAR_COMMAND = "/goal clear"
DEVIN_CLI_GOAL_MAX_TURNS = 50

# `devin acp` serves the host as an Agent Client Protocol agent over stdio, so
# LoopX Chat reaches it through the shared ACP adapter instead of a second
# transport. The global `--permission-mode` flag must precede the subcommand.
# Both entry points — the interactive goal session and the ACP agent — pin
# `dangerous`, the host's maximum (Bypass Permissions) mode: this deployment
# is a user-authorized controlled environment, so the host applies tool calls
# without prompting instead of LoopX simulating approval. The shared ACP
# adapter still cancels any interactive permission request that does arrive;
# a dangerous session simply does not send them.
DEVIN_CLI_BIN = "devin"
DEVIN_CLI_CHAT_AGENT_ID = "devin-cli"
DEVIN_CLI_CHAT_DISPLAY_NAME = "Devin CLI"
DEVIN_CLI_CHAT_ACP_SUBCOMMAND = "acp"
DEVIN_CLI_CHAT_ADAPTER_KIND = "acp"
DEVIN_CLI_PERMISSION_MODE_FLAG = "--permission-mode"
DEVIN_CLI_PERMISSION_MODE = "dangerous"

# ACP mode deliberately does not reuse the local CLI credentials, so an
# unauthenticated `session/new` must point at the host-provided credential
# path rather than at the protocol error readback.
DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION = (
    "Authenticate the Devin CLI ACP host, then retry this session: set "
    "`WINDSURF_API_KEY` in the LoopX Chat service environment and restart "
    "the service. Never paste the API key into this conversation."
)

DEVIN_CLI_NATIVE_GOAL_FACTS = (
    "native `/goal <objective>` command: the host keeps working the objective "
    "across turns in the same session, continuing automatically each time a "
    "turn ends, until it reports the goal complete or blocked",
    f"a goal run pauses itself after {DEVIN_CLI_GOAL_MAX_TURNS} turns; "
    "`/goal` alone shows its status, `/goal resume` continues after an "
    "interrupt, and `/goal clear` drops it",
    "the goal primitive lives in the local interactive session; a one-shot "
    "prompt invocation carries no goal loop, so LoopX binds the live session "
    "instead of spawning host processes",
)

DEVIN_CLI_AGENT_TYPE_CATALOG_ENTRY: dict[str, Any] = {
    "display_name": "Devin CLI",
    "host_loop": (
        "Devin CLI native /goal same-session loop (LoopX quota entry advisory; "
        "the host pauses a run after 50 turns)"
    ),
    "entry": f"/loopx <task> from the LoopX skill installed in {SKILLS_ROOT_LABEL}",
    "accepted_inputs": list(DEVIN_CLI_ACCEPTED_INPUTS),
}


def devin_cli_activation_extras() -> dict[str, Any]:
    """Keyword overrides for ``devin_cli_activation``'s facade call.

    Keeps the Devin CLI host facts (goal command, turn cap, resume/clear
    commands, gate text, activation steps) in this package instead of growing
    ``host_loop_activation.py`` past its module metric budget. Devin CLI ships a
    native same-session goal primitive — ``/goal <objective>`` keeps the live
    session working across turns until it reports complete or blocked, and the
    host pauses the run itself after 50 turns. What it does not ship is a
    LoopX-reachable hook or a way for the CLI to set a goal inside a running
    session, so quota pacing is instructed rather than enforced.
    """
    return {
        "activation_method": "bind_native_goal_with_advisory_quota_entry",
        "extra_host_mutation": {
            "host_loop_primitive": "devin-cli-/goal-same-session-loop",
            "loop_driver": "devin_cli_native_goal_loop",
            "quota_gate_enforcement": "advisory_only",
            "native_goal_command": DEVIN_CLI_GOAL_COMMAND,
            "native_goal_resume_command": DEVIN_CLI_GOAL_RESUME_COMMAND,
            "native_goal_clear_command": DEVIN_CLI_GOAL_CLEAR_COMMAND,
            "native_goal_max_turns": DEVIN_CLI_GOAL_MAX_TURNS,
            "native_goal_facts": list(DEVIN_CLI_NATIVE_GOAL_FACTS),
            "permission_mode": DEVIN_CLI_PERMISSION_MODE,
            "permission_scope": "maximum_bypass",
            "goal_session_start_command": DEVIN_CLI_GOAL_SESSION_START_COMMAND,
            "execution_permission": {
                "scope": "maximum_bypass",
                "mode": DEVIN_CLI_PERMISSION_MODE,
                "owner": "user",
                "enforcement": "required_start_command",
                "start_command": DEVIN_CLI_GOAL_SESSION_START_COMMAND,
            },
            "missing_host_tool_gate": (
                "Devin CLI's /goal loop runs only inside its live interactive "
                "session; LoopX cannot type, resume, or clear a goal in that "
                "session on the user's behalf, and no LoopX hook intercepts a "
                "native continuation, so `quota should-run` entry is advisory "
                "guidance rather than a host-enforced gate. If the session "
                "cannot keep entering through `quota should-run`, show the "
                "exact heartbeat-prompt command for the user to run and do "
                "not claim unattended heartbeat support. The "
                "`--permission-mode dangerous` launch is a user-authorized "
                "controlled-environment configuration, not a LoopX sandbox."
            ),
        },
        "extra_activation_steps": [
            f"Run the session under the authorized maximum permission mode: "
            f"start it with `{DEVIN_CLI_GOAL_SESSION_START_COMMAND}`, enter the "
            f"task through `/loopx`, then bind the objective with the native "
            "goal command — the user, or the current host through its own "
            f"command path, sets `{DEVIN_CLI_GOAL_COMMAND} <task_body>` in this "
            "Devin CLI session. The same session keeps working the objective "
            "across turns until it reports complete or blocked, and the host "
            f"pauses the run itself after {DEVIN_CLI_GOAL_MAX_TURNS} turns.",
            "`/goal` alone shows the goal's status, "
            f"`{DEVIN_CLI_GOAL_RESUME_COMMAND}` continues an interrupted or "
            f"paused goal, and `{DEVIN_CLI_GOAL_CLEAR_COMMAND}` drops it.",
            "Start every turn and every native goal continuation with `quota "
            "should-run` and honor a stop decision before delivery work — "
            "instructed pacing, not a host-enforced gate.",
            "When the native goal reports complete or blocked, settle LoopX "
            "writeback first and stop; when the run pauses at the host turn "
            "cap with quota still allowing more, let the user or host resume "
            "the same goal instead of starting an unmanaged loop.",
        ],
        "host_scheduler_note": (
            "the native `/goal` same-session loop continues the objective "
            "across turns until complete or blocked and pauses itself after "
            f"{DEVIN_CLI_GOAL_MAX_TURNS} turns; quota should-run entry is "
            "advisory guidance in the facade, not a host-enforced gate."
        ),
    }


def devin_cli_goal_session_command(bin_name: str | None = None) -> tuple[str, ...]:
    """Argv that starts the interactive Devin CLI session LoopX binds.

    Carries the same permission pin as the ACP agent — this deployment is a
    user-authorized controlled environment running the host's maximum (Bypass
    Permissions) mode, and the goal session must agree with the chat agent on
    it. No prompt flag: the native goal loop only exists inside the live
    interactive session.
    """
    return (
        bin_name or DEVIN_CLI_BIN,
        DEVIN_CLI_PERMISSION_MODE_FLAG,
        DEVIN_CLI_PERMISSION_MODE,
    )


DEVIN_CLI_GOAL_SESSION_START_COMMAND = " ".join(devin_cli_goal_session_command())


def devin_cli_chat_command(bin_name: str | None = None) -> tuple[str, ...]:
    """Argv that starts Devin CLI as an ACP stdio agent for LoopX Chat.

    ``bin_name`` is an injection point for tests and for an owner whose host
    binary is not on ``PATH`` under the documented name; the default is the
    documented executable. The permission mode is pinned to ``dangerous`` —
    the host's maximum, Bypass Permissions mode — under the same user-authorized
    controlled-environment contract the interactive goal session carries.
    """
    return (
        bin_name or DEVIN_CLI_BIN,
        DEVIN_CLI_PERMISSION_MODE_FLAG,
        DEVIN_CLI_PERMISSION_MODE,
        DEVIN_CLI_CHAT_ACP_SUBCOMMAND,
    )


def devin_home(value: str | None = None) -> Path:
    """The Devin CLI home: ``$XDG_CONFIG_HOME/devin``, else ``~/.config/devin``.

    Devin CLI discovers global skills from ``<devin_home>/skills/<name>/SKILL.md``
    (workspace skills live in ``.devin/skills``). The host follows the XDG base
    directory convention and documents no home override of its own, so the
    resolution order is: explicit injected ``value``, ``XDG_CONFIG_HOME``, then
    the default. Install and uninstall share this one resolver, so they cannot
    target different roots.
    """
    if value:
        return Path(value).expanduser()
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return (Path(xdg_config_home) / "devin").expanduser()
    return (Path.home() / ".config" / "devin").expanduser()
