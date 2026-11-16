"""End-to-end host contract for the Devin CLI surface.

Installing discoverable files is not the same as being a usable LoopX host. The
generated `/loopx` facade tells the agent to run `start-goal ... --host-surface
<exact-current-host>`, so these tests execute that path for real: if devin-cli
is missing from the CLI choices, the selection gate or the activation dispatch,
the facade dead-ends at argparse and the surface is decorative.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from host_surface_cli_probes import (
    onboarding_setup_command_installs,
    selection_gate_offers_surface,
    start_goal_accepts_surface,
)

from loopx.agent_onboarding import _start_instruction, _surface_install_command
from loopx.capabilities.project_skill_delivery import (
    PROJECT_SKILL_SURFACE_ROOTS,
    PROJECT_SKILL_SURFACES,
)
from loopx.chat_acp import ACPStdioAdapter
from loopx.chat_actions import ChatActionService
from loopx.chat_endpoints import RESERVED_AGENT_IDS, AgentEndpointRegistry
from loopx.chat_runtime import ChatRuntimeController
from loopx.chat_store import ChatSessionStore
from loopx.cli_commands._host_thread import HOST_THREAD_ID_ENV
from loopx.devin_cli_goal_mode import (
    DEVIN_CLI_ACCEPTED_INPUTS,
    DEVIN_CLI_AGENT_TYPE_CATALOG_ENTRY,
    DEVIN_CLI_BIN,
    DEVIN_CLI_CHAT_AGENT_ID,
    DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION,
    DEVIN_CLI_GOAL_CLEAR_COMMAND,
    DEVIN_CLI_GOAL_COMMAND,
    DEVIN_CLI_GOAL_MAX_TURNS,
    DEVIN_CLI_GOAL_RESUME_COMMAND,
    DEVIN_CLI_NATIVE_GOAL_FACTS,
    SKILLS_ROOT_LABEL as DEVIN_CLI_SKILLS_ROOT_LABEL,
    devin_cli_activation_extras,
    devin_cli_chat_command,
    devin_home,
)
from loopx.host_loop_activation import (
    _heartbeat_commands,
    agent_type_for_host_surface,
    build_agent_type_catalog,
    build_host_loop_activation_packet,
    normalize_agent_type,
    scheduler_command_binding_for_agent_type,
)
from loopx.slash_command_files import MANAGED_MARKER_PREFIX
from loopx.slash_command_install import install_slash_commands

HOST_SURFACE = "devin-cli"
INSTALL_SURFACE = "devin"


def test_start_goal_accepts_the_devin_cli_host_surface(tmp_path: Path) -> None:
    payload = start_goal_accepts_surface(HOST_SURFACE, tmp_path)
    activation = payload["command_pack"]["host_loop_activation"]
    assert activation["host_surface"] == "devin_cli_native_goal_mode"


def test_host_selection_gate_offers_devin_cli_and_its_rerun_command_works(
    tmp_path: Path,
) -> None:
    selection_gate_offers_surface(HOST_SURFACE, tmp_path)


def test_agent_onboarding_setup_command_installs_into_the_xdg_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The setup command carries no home flag, so the resolver must read the
    same XDG root the running host reads."""
    monkeypatch.delenv("LOOPX_SKILLS_DIR", raising=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }
    if "PYTHONPATH" in os.environ:  # keep hermetic when run from a worktree
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]

    onboarding_setup_command_installs(
        HOST_SURFACE,
        outside,
        env,
        expected_skill=(
            tmp_path / "xdg" / "devin" / "skills" / "loopx" / "SKILL.md"
        ),
    )


def test_agent_onboarding_setup_command_falls_back_to_home_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without XDG_CONFIG_HOME the documented default is ~/.config/devin."""
    monkeypatch.delenv("LOOPX_SKILLS_DIR", raising=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
    }
    if "PYTHONPATH" in os.environ:
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]

    onboarding_setup_command_installs(
        HOST_SURFACE,
        outside,
        env,
        expected_skill=(
            tmp_path / "home" / ".config" / "devin" / "skills" / "loopx" / "SKILL.md"
        ),
    )


def test_devin_home_resolves_xdg_then_the_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XDG_CONFIG_HOME is the host's documented root override; an injected
    value still wins, and the default is ~/.config/devin, not a dotfile home."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert devin_home() == tmp_path / "home" / ".config" / "devin"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert devin_home() == tmp_path / "xdg" / "devin"
    assert devin_home(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_install_and_uninstall_follow_xdg_not_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HOME and XDG_CONFIG_HOME differ, so a resolver that ignores XDG writes
    where the running host never looks while still reporting success."""
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    payload = install_slash_commands(execute=True, surfaces=[INSTALL_SURFACE])
    assert payload["ok"] is True

    installed_skill = xdg / "devin" / "skills" / "loopx" / "SKILL.md"
    assert installed_skill.is_file(), "install must target the resolved XDG root"
    assert not (home / ".config" / "devin").exists(), (
        "install must not touch the default root"
    )
    assert MANAGED_MARKER_PREFIX in installed_skill.read_text(encoding="utf-8")

    removed = install_slash_commands(
        execute=True,
        surfaces=[INSTALL_SURFACE],
        uninstall=True,
    )
    assert removed["ok"] is True
    assert not installed_skill.exists(), "uninstall must use the same resolved root"


def test_installed_skills_are_invocable_as_devin_slash_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devin exposes every discovered skill as `/<skill-name>`, so the reported
    invocation must be the slash form the user actually types."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],  # the agent-type spelling resolves to the surface
        devin_home=str(tmp_path / "devin-home"),
    )
    assert payload["ok"] is True
    assert payload["effective_surfaces"] == [INSTALL_SURFACE]
    rows = {
        item["command"]: item
        for item in payload["installed"]
        if item["surface"] == INSTALL_SURFACE
    }
    assert rows["/loopx"]["invoke_as"] == ["/loopx"]
    assert rows["/loopx"]["mechanism"] == "devin_cli_skills"
    assert rows["/loopx"]["host_surfaces"] == [HOST_SURFACE]
    assert (
        payload["summary"]["devin_cli_skill_dir"]
        == str(tmp_path / "devin-home" / "skills")
    )
    assert (
        tmp_path / "devin-home" / "skills" / "loopx" / "SKILL.md"
    ).is_file()


def test_devin_is_opt_in_not_part_of_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Like every host that owns a separate config root, devin only installs
    when named; the default `all` set must not write into it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    payload = install_slash_commands(
        execute=True,
        surfaces=["all"],
        codex_home=str(tmp_path / "codex"),
        claude_home=str(tmp_path / "claude"),
        opencode_home=str(tmp_path / "opencode"),
    )
    assert payload["ok"] is True
    assert not (tmp_path / "xdg" / "devin").exists()
    assert not any(
        item["surface"] == INSTALL_SURFACE for item in payload["installed"]
    )


def test_installer_preserves_user_owned_devin_skill(tmp_path: Path) -> None:
    """The skills root is shared with the user's own skills; an unmarked file
    must never be overwritten, and a rerun over a managed file is a no-op."""
    skills_dir = tmp_path / "devin-home" / "skills"
    skill_path = skills_dir / "loopx" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("user-owned skill body\n", encoding="utf-8")

    payload = install_slash_commands(
        execute=True,
        surfaces=[INSTALL_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    statuses = {
        (item["surface"], item["command"]): item["status"]
        for item in payload["installed"]
    }
    assert statuses[(INSTALL_SURFACE, "/loopx")] == "skipped_user_file"
    assert skill_path.read_text(encoding="utf-8") == "user-owned skill body\n"

    retire = install_slash_commands(
        execute=True,
        uninstall=True,
        surfaces=[INSTALL_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    assert skill_path.exists(), "uninstall must not retire a user-owned file"
    assert retire["ok"] is True


def test_agent_type_catalog_and_scheduler_binding() -> None:
    """Devin CLI reuses the generic CLI runtime profile: its same-session
    `/goal` loop is settled through the shared generic accounting, not a
    Devin-specific profile."""
    catalog = build_agent_type_catalog()
    entry = next(
        item
        for item in catalog["canonical_agent_types"]
        if item["agent_type"] == HOST_SURFACE
    )
    assert entry["display_name"] == "Devin CLI"
    assert "advisory" in entry["host_loop"].lower()
    assert "50" in entry["host_loop"]
    for accepted in DEVIN_CLI_ACCEPTED_INPUTS:
        assert accepted in entry["accepted_inputs"]
        assert normalize_agent_type(accepted) == HOST_SURFACE
    assert normalize_agent_type("Devin CLI") == HOST_SURFACE
    assert agent_type_for_host_surface("devin") == HOST_SURFACE
    assert agent_type_for_host_surface(HOST_SURFACE) == HOST_SURFACE
    assert scheduler_command_binding_for_agent_type(HOST_SURFACE) == {
        "runtime_profile": "generic_cli"
    }


def test_activation_binds_native_goal_with_advisory_quota_entry() -> None:
    """Devin CLI owns a native same-session goal primitive: `/goal <objective>`
    keeps the live session working across turns until it reports complete or
    blocked, and the host pauses the run itself after 50 turns. The packet has
    to state exactly that envelope — a real goal binding, advisory quota
    pacing, the host's own turn cap — without claiming LoopX can type into the
    host's session or intercept a native continuation."""
    packet = build_host_loop_activation_packet(
        agent_type=HOST_SURFACE,
        goal_id="surface-goal",
        agent_id="probe-agent",
        registered_agents=["probe-agent"],
    )
    assert packet["activation_method"] == "bind_native_goal_with_advisory_quota_entry"
    mutation = packet["host_mutation"]
    assert mutation["cli_can_mutate_directly"] is False
    # The native primitive is real and must be named, not denied.
    assert mutation["host_loop_primitive"] == "devin-cli-/goal-same-session-loop"
    assert mutation["loop_driver"] == "devin_cli_native_goal_loop"
    # The quota claim must be honest: advisory guidance, no installed hook.
    assert mutation["quota_gate_enforcement"] == "advisory_only"
    assert mutation["native_goal_command"] == DEVIN_CLI_GOAL_COMMAND
    assert mutation["native_goal_resume_command"] == DEVIN_CLI_GOAL_RESUME_COMMAND
    assert mutation["native_goal_clear_command"] == DEVIN_CLI_GOAL_CLEAR_COMMAND
    assert mutation["native_goal_max_turns"] == DEVIN_CLI_GOAL_MAX_TURNS
    assert DEVIN_CLI_GOAL_MAX_TURNS == 50
    gate = mutation["missing_host_tool_gate"]
    assert "advisory" in gate
    assert "cannot" in gate

    steps = " ".join(packet["activation_steps"])
    assert f"`{DEVIN_CLI_GOAL_COMMAND} <task_body>`" in steps
    assert str(DEVIN_CLI_GOAL_MAX_TURNS) in steps
    assert "quota should-run" in steps
    assert DEVIN_CLI_GOAL_RESUME_COMMAND in steps
    assert DEVIN_CLI_GOAL_CLEAR_COMMAND in steps
    assert "complete or blocked" in steps

    assert packet["setup_command"] == _surface_install_command(
        HOST_SURFACE, "loopx", "."
    )
    assert packet["setup_command"].endswith(
        f"slash-commands --install --surface {INSTALL_SURFACE}"
    )
    assert "quota should-run" in _start_instruction(HOST_SURFACE)
    assert DEVIN_CLI_GOAL_COMMAND in _start_instruction(HOST_SURFACE)
    assert (
        packet["entry_command_hint"]
        == f"the LoopX skill installed in {DEVIN_CLI_SKILLS_ROOT_LABEL}"
    )
    # Rendered heartbeat commands and scope must carry no machine-gate semantics.
    assert "gated" not in packet["activation_input_command"].lower()
    assert "advisory" in packet["activation_input_command"].lower()
    hb = _heartbeat_commands(
        goal_id="surface-goal",
        agent_type=HOST_SURFACE,
        cli_bin="loopx",
        agent_id="probe-agent",
    )
    assert "gated" not in hb["heartbeat_prompt"].lower()
    assert "gated" not in hb["heartbeat_prompt_json"].lower()
    assert "advisory" in hb["heartbeat_prompt"].lower()
    assert "advisory" in hb["heartbeat_prompt_json"].lower()


def test_no_prompt_invocation_path_is_projected() -> None:
    """The surface binds the live interactive session's native goal loop. Any
    packet or instruction projecting a one-shot prompt flag would send the
    agent down a path that carries no goal loop at all."""

    def strings(value: object) -> list[str]:
        found: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, str):
                found.append(node)
            elif isinstance(node, dict):
                for item in node.values():
                    walk(item)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)

        walk(value)
        return found

    consumers = {
        "activation packet": build_host_loop_activation_packet(
            agent_type=HOST_SURFACE, goal_id="surface-goal"
        ),
        "activation extras": devin_cli_activation_extras(),
        "native goal facts": DEVIN_CLI_NATIVE_GOAL_FACTS,
        "catalog entry": DEVIN_CLI_AGENT_TYPE_CATALOG_ENTRY,
        "onboarding recommended start": _start_instruction(HOST_SURFACE),
        "installer notes": install_slash_commands(
            execute=False, surfaces=[INSTALL_SURFACE]
        )["notes"],
    }
    for label, value in consumers.items():
        for text in strings(value):
            assert "devin -p" not in text, f"{label} projects a prompt invocation"
            assert "--print" not in text, f"{label} projects a prompt invocation"


def test_devin_cli_project_skill_root() -> None:
    """Devin reads workspace skills from .devin/skills, so project-level
    delivery has a real target root."""
    assert HOST_SURFACE in PROJECT_SKILL_SURFACES
    assert PROJECT_SKILL_SURFACE_ROOTS[HOST_SURFACE] == Path(".devin") / "skills"


def _executable_stub(path: Path) -> Path:
    """A file that only has to satisfy the runtime's PATH availability probe."""
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_dashboard_lists_devin_cli_as_a_builtin_chat_agent(tmp_path: Path) -> None:
    """`loopx dashboard` renders its Agent picker from the running process's
    capability rows, so Devin CLI is only reachable there if it appears as a
    built-in row with an adapter the runtime can start. Devin CLI serves an
    ACP agent, so the row must be ACP-shaped — and its id must be reserved, or
    an owner-local endpoint could shadow the built-in adapter. The command
    pins `--permission-mode auto` (read-only tools only) before the `acp`
    subcommand so the session never inherits a broader mode from the owner's
    config; host allow rules and read commands are still not a LoopX sandbox,
    so the row honestly scopes to workspace_write."""
    controller = ChatRuntimeController(
        store=ChatSessionStore(tmp_path / "runtime"),
        codex_bin="loopx-missing-codex-for-test",
        devin_cli_bin=str(_executable_stub(tmp_path / "devin")),
    )
    try:
        rows = controller.capabilities()
        row = next(
            item for item in rows if item["agent_id"] == DEVIN_CLI_CHAT_AGENT_ID
        )
        assert row["source"] == "builtin"
        assert row["adapter_kind"] == "acp"
        assert row["display_name"] == "Devin CLI"
        assert row["trust_scope"] == "workspace_write"
        assert row["streaming"] is True
        assert row["resume"] is True
        assert row["interrupt"] is True
        assert row["tool_calls"] is True
        assert row["available"] is True
    finally:
        controller.close()

    command = devin_cli_chat_command("devin")
    assert command == ("devin", "--permission-mode", "auto", "acp")
    # The global flag must precede the subcommand, and the argv must never
    # reach a prompt path or a broad auto-approve mode.
    assert command.index("--permission-mode") < command.index("acp")
    for token in ("-p", "--print", "dangerous", "accept-edits", "smart"):
        assert token not in command
    assert devin_cli_chat_command() == (
        DEVIN_CLI_BIN, "--permission-mode", "auto", "acp"
    )

    assert DEVIN_CLI_CHAT_AGENT_ID in RESERVED_AGENT_IDS
    with pytest.raises(ValueError, match="reserved"):
        AgentEndpointRegistry(tmp_path / "endpoints").upsert(
            {
                "agent_id": DEVIN_CLI_CHAT_AGENT_ID,
                "display_name": "Shadow Devin",
                "command": ["devin", "acp"],
            }
        )


def test_missing_devin_cli_renders_as_needing_configuration(
    tmp_path: Path,
) -> None:
    """An uninstalled host must render as unavailable rather than failing when
    a session opens; `available` is a live probe, not a static claim."""
    controller = ChatRuntimeController(
        store=ChatSessionStore(tmp_path / "runtime"),
        codex_bin="loopx-missing-codex-for-test",
        devin_cli_bin="loopx-missing-devin-cli-for-test",
    )
    try:
        row = next(
            item
            for item in controller.capabilities()
            if item["agent_id"] == DEVIN_CLI_CHAT_AGENT_ID
        )
        assert row["available"] is False
    finally:
        controller.close()


def test_start_adapter_dispatches_the_devin_acp_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime branch must launch the Devin command through the shared ACP
    adapter with the same resume/timeout/config plumbing as every ACP host —
    a dispatch that drops `resume_thread_id` would silently break session
    recovery."""
    captured: dict[str, object] = {}

    def fake_start(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ACPStdioAdapter, "start", classmethod(lambda cls, **kw: fake_start(**kw)))

    controller = ChatRuntimeController(
        store=ChatSessionStore(tmp_path / "runtime"),
        codex_bin="loopx-missing-codex-for-test",
        devin_cli_bin="devin-under-test",
        startup_timeout_sec=12.0,
        idle_timeout_sec=34.0,
        hard_timeout_sec=56.0,
    )
    try:
        controller._start_adapter(
            agent_id=DEVIN_CLI_CHAT_AGENT_ID,
            work_dir=tmp_path,
            goal_id=None,
            objective="probe",
            resume_thread_id="devin-session-1",
            execution_mode=True,
            agent_config={"mode": "plan"},
        )
    finally:
        controller.close()

    assert captured["command"] == (
        "devin-under-test", "--permission-mode", "auto", "acp"
    )
    assert captured["work_dir"] == tmp_path
    assert captured["resume_thread_id"] == "devin-session-1"
    assert captured["startup_timeout_sec"] == 12.0
    assert captured["idle_timeout_sec"] == 34.0
    assert captured["hard_timeout_sec"] == 56.0
    assert captured["execution_mode"] is True
    assert captured["config_values"] == {"mode": "plan"}
    assert captured["authentication_next_action"] == (
        DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION
    )
    assert "devin auth login" not in DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION
    assert "WINDSURF_API_KEY" in DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION
    assert "restart" in DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION
    assert "Never paste the API key" in DEVIN_CLI_CHAT_AUTHENTICATION_NEXT_ACTION


def test_devin_cli_is_recognized_across_the_control_plane() -> None:
    """A durable Goal agent id is operator-chosen, so the Endpoint resolves
    through its host family exactly as `codex` resolves `codex-main-control`.
    Matching stays bounded at the `-` delimiter: `devinvoice-worker` is not a
    Devin session. Devin exports no ambient session id for the CLI host, so
    it must not appear in the thread-env table — the ACP adapter persists its
    own session id instead."""
    assert ChatActionService._agent_family("devin-cli") == DEVIN_CLI_CHAT_AGENT_ID
    assert ChatActionService._agent_family("devin") == DEVIN_CLI_CHAT_AGENT_ID
    assert ChatActionService._agent_family("devin-worker-1") == DEVIN_CLI_CHAT_AGENT_ID
    assert ChatActionService._agent_family("Devin_CLI") == DEVIN_CLI_CHAT_AGENT_ID
    assert ChatActionService._agent_family("devinvoice-worker") == "devinvoice-worker"
    assert ChatActionService._agent_family("devinexplorer") == "devinexplorer"
    assert HOST_SURFACE not in HOST_THREAD_ID_ENV
