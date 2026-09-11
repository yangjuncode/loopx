from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEVIN_CLI_INSTALL_SURFACE = "devin-cli"
DEVIN_CLI_AGENT_TYPE = "devin-cli"
DEFAULT_DEVIN_CLI_HOME = ".config/devin"
# Devin CLI follows XDG conventions for its global root: skills live under
# `~/.config/devin/skills/<name>/SKILL.md` (or `%APPDATA%\devin\skills` on
# Windows). The host documents no dedicated home override, but `XDG_CONFIG_HOME`
# relocates the whole `~/.config` tree, so LoopX resolves it the same way the
# host does instead of hardcoding `~/.config`.
DEVIN_CLI_HOME_ENV = "XDG_CONFIG_HOME"
SKILLS_SUBDIR = "skills"
SKILLS_ROOT_LABEL = "~/.config/devin/skills"
DEVIN_CLI_BIN = "devin"
DEVIN_CLI_ACCEPTED_INPUTS = (
    "devin-cli",
    "devin_cli",
    "devin cli",
    "devincli",
    "devin",
)

# Native in-session automation primitive Devin CLI ships (verified against the
# published docs at the devin-cli skill/hook reference, version 3000.10.21).
# `/loop <prompt>` runs a prompt then auto-reviews the diff in a loop; it
# requires clean git state to start. The loop lives and dies with the session
# — there is no cross-session daemon — so LoopX binds the objective to the
# host's own `/loop` instead of pretending the agent merely drives itself.
DEVIN_CLI_LOOP_COMMAND = "/loop"
DEVIN_CLI_LOOP_DESCRIPTION = (
    "Run a prompt then auto-review the diff in a loop "
    "(requires clean git state to start)."
)

# Lifecycle hooks the host contracts (verified against the published
# `extensibility/hooks` reference). `Stop` can block the agent from stopping
# (exit code 2 or `decision: block`), and `PreToolUse` can block or rewrite a
# tool call. LoopX installs no hook today, so quota pacing stays advisory; the
# seam is recorded here so the honest claim and the future binding point stay
# in one place instead of being rediscovered from host docs.
DEVIN_CLI_HOOK_TRIGGERS = (
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "UserPromptSubmit",
    "Stop",
    "PostCompaction",
    "SessionStart",
    "SessionEnd",
)

# The host stamps every session with a stable id, which is what a LoopX thread
# binding can key on instead of prose.
DEVIN_CLI_SESSION_ID_ENV = "DEVIN_SESSION_ID"

DEVIN_CLI_NATIVE_LOOP_FACTS = (
    "native `/loop <prompt>` command: the host re-runs the prompt and "
    "auto-reviews the diff in a loop, requiring clean git state to start; "
    "the loop lives and dies with the session, there is no cross-session "
    "daemon",
    "lifecycle hooks (`PreToolUse`, `PostToolUse`, `PermissionRequest`, "
    "`UserPromptSubmit`, `Stop`, `PostCompaction`, `SessionStart`, "
    "`SessionEnd`) run user or project automation on tool and session "
    "events; `Stop` can block the agent from stopping (exit code 2 or "
    "`decision: block`) and `PreToolUse` can block or rewrite a tool call",
    "skills are discovered from `~/.config/devin/skills/<name>/SKILL.md` "
    "(global) or `.devin/skills/<name>/SKILL.md` (project) and invoked via "
    "`/<skill-name>`; the LoopX skill facade is the entry LoopX reaches",
)

DEVIN_CLI_AGENT_TYPE_CATALOG_ENTRY: dict[str, Any] = {
    "display_name": "Devin CLI",
    "host_loop": (
        "Devin CLI native /loop diff-review loop (LoopX quota pacing is "
        "advisory)"
    ),
    "entry": f"/loopx <task> from the LoopX skill installed in {SKILLS_ROOT_LABEL}",
    "accepted_inputs": list(DEVIN_CLI_ACCEPTED_INPUTS),
}


def devin_cli_activation_extras() -> dict[str, Any]:
    """Keyword overrides for ``devin_cli_activation``'s facade call.

    Keeps the Devin CLI host facts (loop command, hook triggers, gate text,
    activation steps) in the devin_cli package instead of growing
    ``host_loop_activation.py`` past its module metric budget. Devin CLI
    ships one half of a goal-mode host natively: a `/loop <prompt>` primitive
    whose host-side loop re-runs the prompt and auto-reviews the diff while
    the session lives. What it does not ship is a cross-session daemon, and
    LoopX installs no hook, so quota pacing is instructed rather than
    enforced.
    """
    return {
        "activation_method": "bind_native_loop_with_advisory_quota_entry",
        "extra_host_mutation": {
            "host_loop_primitive": "devin-cli-/loop-diff-review-loop",
            "loop_driver": "devin_cli_native_loop",
            "quota_gate_enforcement": "advisory_only",
            "native_loop_command": DEVIN_CLI_LOOP_COMMAND,
            "host_session_id_env": DEVIN_CLI_SESSION_ID_ENV,
            "host_hook_triggers": list(DEVIN_CLI_HOOK_TRIGGERS),
            "missing_host_tool_gate": (
                "Devin CLI's /loop runs only while the CLI session is "
                "alive; there is no cross-session daemon. LoopX installs "
                "no Devin hook, so no host hook intercepts a native loop "
                "iteration and quota pacing is advisory: the facade "
                "instructs, it cannot enforce. If the loop stops with work "
                "remaining, show the exact heartbeat-prompt command for the "
                "user to run and do not claim unattended heartbeat support."
            ),
        },
        "extra_activation_steps": [
            "Bind the objective with the native loop command: "
            f"`{DEVIN_CLI_LOOP_COMMAND} <task_body>` — Devin CLI re-runs "
            "the prompt and auto-reviews the diff in a loop; the loop "
            "requires clean git state to start, so commit or stash "
            "unrelated changes before binding.",
            "Start every turn and native loop iteration with `quota "
            "should-run` and honor a stop/throttle decision before any "
            "delivery work — instructed pacing, not a host-enforced gate.",
            "When the loop stops with work remaining and quota allows more, "
            "re-arm one further bounded `/loop` invocation instead of "
            "free-running, and re-enter through `quota should-run` on the "
            "same advisory basis.",
        ],
        "host_scheduler_note": (
            "the native `/loop` diff-review loop drives this session; "
            "quota should-run entry is advisory guidance in the facade, "
            "not a host-enforced gate."
        ),
    }


def devin_home(value: str | None = None) -> Path:
    """The Devin CLI home: ``XDG_CONFIG_HOME/devin`` when set, else
    ``~/.config/devin``.

    Devin CLI follows XDG conventions: global skills live under
    ``~/.config/devin/skills/<name>/SKILL.md`` (or ``%APPDATA%\\devin\\skills``
    on Windows). The host documents no dedicated home override, but
    ``XDG_CONFIG_HOME`` relocates the whole ``~/.config`` tree, so LoopX
    resolves it the same way the host does. Resolution order matches every
    other host in this repository: explicit injected ``value`` (the full devin
    home, e.g. ``~/.config/devin``), then the host environment override
    (``XDG_CONFIG_HOME`` + ``devin``), then the default. Install and uninstall
    share this one resolver, so they cannot target different roots.
    """
    if value:
        return Path(value).expanduser()
    xdg = os.environ.get(DEVIN_CLI_HOME_ENV)
    if xdg:
        return Path(xdg).expanduser() / "devin"
    return Path.home() / ".config" / "devin"
