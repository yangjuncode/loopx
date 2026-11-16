from __future__ import annotations

from importlib import resources

# Pi ships no sandbox or per-tool approval layer: the bundled tools (read,
# bash, edit, write) run with the launching OS user's permissions directly.
# `--approve` only pre-approves the project trust prompt, so the session does
# not stall on it — that combination is Pi's maximum execution boundary.
PI_BIN = "pi"
PI_PROJECT_TRUST_FLAG = "--approve"


def pi_goal_session_command(bin_name: str | None = None) -> tuple[str, ...]:
    """Argv that starts the Pi session LoopX binds — project trust pre-approved."""
    return (bin_name or PI_BIN, PI_PROJECT_TRUST_FLAG)


PI_GOAL_SESSION_START_COMMAND = " ".join(pi_goal_session_command())
PI_PERMISSION_FACT = (
    "Pi's bundled tools (read, bash, edit, write) run with the launching OS "
    "user's permissions directly — the host performs no per-tool approval, and "
    "`--approve` only pre-approves the project trust prompt."
)


def extension_source() -> str:
    return resources.files(__package__).joinpath("loopx-goal.ts").read_text(encoding="utf-8")


def runtime_source() -> str:
    return resources.files(__package__).joinpath("pi-goal-loop-runtime.mjs").read_text(
        encoding="utf-8"
    )
