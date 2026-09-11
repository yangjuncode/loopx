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
import yaml
from host_surface_cli_probes import (
    onboarding_setup_command_installs,
    selection_gate_offers_surface,
    start_goal_accepts_surface,
)

from loopx.agent_onboarding import _start_instruction, _surface_install_command
from loopx.devin_cli_goal_mode import (
    DEVIN_CLI_HOOK_TRIGGERS,
    DEVIN_CLI_LOOP_COMMAND,
    DEVIN_CLI_NATIVE_LOOP_FACTS,
    DEVIN_CLI_SESSION_ID_ENV,
    SKILLS_ROOT_LABEL,
    devin_home,
)
from loopx.host_loop_activation import (
    _heartbeat_commands,
    build_agent_type_catalog,
    build_host_loop_activation_packet,
    normalize_agent_type,
    scheduler_command_binding_for_agent_type,
)
from loopx.slash_command_install import install_slash_commands

HOST_SURFACE = "devin-cli"


def test_start_goal_accepts_the_devin_cli_host_surface(tmp_path: Path) -> None:
    payload = start_goal_accepts_surface(HOST_SURFACE, tmp_path)
    activation = payload["command_pack"]["host_loop_activation"]
    assert activation["host_surface"] == "devin_cli_agent_loop"


def test_host_selection_gate_offers_devin_cli_and_its_rerun_command_works(
    tmp_path: Path,
) -> None:
    selection_gate_offers_surface(HOST_SURFACE, tmp_path)


def test_agent_onboarding_setup_command_installs_the_devin_cli_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOOPX_SKILLS_DIR", raising=False)
    monkeypatch.delenv(DEVIN_CLI_SESSION_ID_ENV, raising=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
    }
    if "PYTHONPATH" in os.environ:  # keep hermetic when run from a worktree
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]

    # Devin CLI follows XDG conventions: global skills live under
    # ~/.config/devin/skills/<name>/SKILL.md, the per-skill directory layout,
    # not one flat file per skill.
    onboarding_setup_command_installs(
        HOST_SURFACE,
        outside,
        env,
        expected_skill=(
            tmp_path / "home" / ".config" / "devin" / "skills" / "loopx" / "SKILL.md"
        ),
    )


def test_devin_home_resolves_xdg_config_home_then_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devin CLI follows XDG conventions: skills live under
    ~/.config/devin/skills. The host documents no dedicated home override, but
    XDG_CONFIG_HOME relocates the whole ~/.config tree, so LoopX resolves it
    the same way the host does. Resolution order matches every other host:
    injected value, host environment override (XDG_CONFIG_HOME), default.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(DEVIN_CLI_SESSION_ID_ENV, raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert devin_home() == tmp_path / "home" / ".config" / "devin"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert devin_home() == tmp_path / "xdg" / "devin"
    # An explicit injected value is the full devin home, not the XDG root.
    assert devin_home(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_install_and_uninstall_follow_the_xdg_override_not_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real failure this guards: install reporting success outside the
    active profile. HOME and XDG_CONFIG_HOME differ, so a resolver that
    ignores the override writes where the running host never looks."""
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    payload = install_slash_commands(execute=True, surfaces=[HOST_SURFACE])
    assert payload["ok"] is True

    installed_skill = xdg / "devin" / "skills" / "loopx" / "SKILL.md"
    assert installed_skill.is_file(), "install must target the resolved host root"
    assert not (home / ".config" / "devin").exists(), (
        "install must not touch the default root"
    )

    reported = {
        item["path"]
        for item in payload["installed"]
        if item["surface"] == HOST_SURFACE and item["path"]
    }
    assert str(installed_skill) in reported, "readback must name the resolved path"

    removed = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        uninstall=True,
    )
    assert removed["ok"] is True
    assert not installed_skill.exists(), "uninstall must use the same resolved root"


def test_installed_skills_are_invocable_as_devin_slash_commands(
    tmp_path: Path,
) -> None:
    """Devin CLI exposes every discovered skill as `/<skill-name>`, so the
    reported invocation must be the slash form the user actually types — a
    bare skill id would send them looking for a menu the host does not have."""
    payload = install_slash_commands(
        execute=True,
        surfaces=["devin"],  # the bare product name must resolve to the surface
        devin_home=str(tmp_path / "devin-home"),
    )
    assert payload["ok"] is True
    assert payload["effective_surfaces"] == [HOST_SURFACE]
    rows = {
        item["command"]: item
        for item in payload["installed"]
        if item["surface"] == HOST_SURFACE
    }
    assert rows["/loopx"]["invoke_as"] == ["/loopx"]
    assert rows["/loopx"]["mechanism"] == "devin_cli_skills"
    assert (
        payload["summary"]["devin_cli_skill_dir"]
        == str(tmp_path / "devin-home" / "skills")
    )
    assert (tmp_path / "devin-home" / "skills" / "loopx" / "SKILL.md").is_file()


def test_installed_skill_front_matter_keeps_names_unquoted(tmp_path: Path) -> None:
    """Devin CLI derives the slash command from the front-matter `name`, and a
    strict YAML reader keeps quote characters verbatim: `name: "loopx"` would
    become the command `/"loopx"`. So the name must be a plain YAML scalar.
    Values YAML genuinely needs quoted (a leading `[`, an embedded `": "`) must
    stay quoted, or a strict reader rejects the whole front matter."""
    install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    skills = sorted((tmp_path / "devin-home" / "skills").glob("*/SKILL.md"))
    assert skills, "installer wrote no skills"
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        front_matter = text.split("---", 2)[1]
        fields = yaml.safe_load(front_matter)
        assert fields["name"] == skill.parent.name
        assert '"' not in fields["name"]
        assert f"name: {skill.parent.name}\n" in text

    # The values that must stay quoted, proven on the shipped specs rather than
    # asserted in the abstract.
    entry = (tmp_path / "devin-home" / "skills" / "loopx" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert 'argument-hint: "[' in entry  # a bare [ would parse as a flow sequence
    research = (
        tmp_path / "devin-home" / "skills" / "loopx-deepresearch" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert 'description: "' in research  # contains ": ", illegal unquoted


def test_project_scope_installs_into_devin_skills_in_project_dir(
    tmp_path: Path,
) -> None:
    """Project scope writes to .devin/skills in the project directory, not
    the global ~/.config/devin/skills root. Only that project's Devin CLI
    sessions discover the skill; other projects are unaffected."""
    project = tmp_path / "my-project"
    project.mkdir()
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_scope="project",
        devin_project=str(project),
        devin_home=str(tmp_path / "global-devin-home"),
    )
    assert payload["ok"] is True
    assert payload["summary"]["devin_cli_scope"] == "project"
    project_skill = project / ".devin" / "skills" / "loopx" / "SKILL.md"
    assert project_skill.is_file(), "project scope must write into .devin/skills"
    assert not (tmp_path / "global-devin-home" / "skills").exists(), (
        "project scope must not touch the global root"
    )
    assert payload["summary"]["devin_cli_skill_dir"] == str(
        project / ".devin" / "skills"
    )

    # Uninstall from project scope must remove the same files.
    removed = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        uninstall=True,
        devin_scope="project",
        devin_project=str(project),
        devin_home=str(tmp_path / "global-devin-home"),
    )
    assert removed["ok"] is True
    assert not project_skill.exists()


def test_agents_project_scope_installs_into_agents_skills_in_project_dir(
    tmp_path: Path,
) -> None:
    """agents-project scope writes to .agents/skills in the project directory
    — the cross-host .agents standard path. Any host supporting .agents
    (Devin CLI, and others) discovers skills there, not just Devin."""
    project = tmp_path / "my-project"
    project.mkdir()
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_scope="agents-project",
        devin_project=str(project),
        devin_home=str(tmp_path / "global-devin-home"),
    )
    assert payload["ok"] is True
    assert payload["summary"]["devin_cli_scope"] == "agents-project"
    project_skill = project / ".agents" / "skills" / "loopx" / "SKILL.md"
    assert project_skill.is_file(), "agents-project scope must write into .agents/skills"
    assert not (project / ".devin" / "skills").exists(), (
        "agents-project scope must not touch .devin/skills"
    )
    assert not (tmp_path / "global-devin-home" / "skills").exists(), (
        "agents-project scope must not touch the global root"
    )
    assert payload["summary"]["devin_cli_skill_dir"] == str(
        project / ".agents" / "skills"
    )

    # Uninstall must remove the same files.
    removed = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        uninstall=True,
        devin_scope="agents-project",
        devin_project=str(project),
        devin_home=str(tmp_path / "global-devin-home"),
    )
    assert removed["ok"] is True
    assert not project_skill.exists()


def test_agents_global_scope_installs_into_home_agents_skills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agents-global scope writes to ~/.agents/skills — the cross-host .agents
    standard global path. It is shared across all projects but not tied to
    Devin's own ~/.config/devin root."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_scope="agents-global",
        devin_home=str(tmp_path / "devin-home"),
    )
    assert payload["ok"] is True
    assert payload["summary"]["devin_cli_scope"] == "agents-global"
    agents_skill = tmp_path / "home" / ".agents" / "skills" / "loopx" / "SKILL.md"
    assert agents_skill.is_file(), "agents-global must write into ~/.agents/skills"
    assert not (tmp_path / "devin-home" / "skills").exists(), (
        "agents-global must not touch ~/.config/devin/skills"
    )
    assert payload["summary"]["devin_cli_skill_dir"] == str(
        tmp_path / "home" / ".agents" / "skills"
    )

    removed = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        uninstall=True,
        devin_scope="agents-global",
        devin_home=str(tmp_path / "devin-home"),
    )
    assert removed["ok"] is True
    assert not agents_skill.exists()


def test_global_scope_is_the_default_when_scope_omitted(tmp_path: Path) -> None:
    """Backward compatibility: when devin_scope is None (not specified), the
    installer writes to the global root, exactly as it did before the
    --devin-scope option existed."""
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    assert payload["ok"] is True
    assert payload["summary"]["devin_cli_scope"] is None
    assert (tmp_path / "devin-home" / "skills" / "loopx" / "SKILL.md").is_file()


def test_project_scope_preserves_user_owned_skill(tmp_path: Path) -> None:
    """Project scope shares .devin/skills with the user's own skills; an
    unmarked file must never be overwritten, and a managed file is upgraded."""
    project = tmp_path / "proj"
    skill_path = project / ".devin" / "skills" / "loopx" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("user-owned skill body\n", encoding="utf-8")

    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_scope="project",
        devin_project=str(project),
    )
    statuses = {
        (item["surface"], item["command"]): item["status"]
        for item in payload["installed"]
    }
    assert statuses[(HOST_SURFACE, "/loopx")] == "skipped_user_file"
    assert skill_path.read_text(encoding="utf-8") == "user-owned skill body\n"


def test_installer_preserves_user_owned_devin_skill(tmp_path: Path) -> None:
    """The skills root is shared with the user's own skills; an unmarked file
    must never be overwritten, and a rerun over a managed file is a no-op."""
    skills_dir = tmp_path / "devin-home" / "skills"
    skill_path = skills_dir / "loopx" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("user-owned skill body\n", encoding="utf-8")

    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    statuses = {
        (item["surface"], item["command"]): item["status"]
        for item in payload["installed"]
    }
    assert statuses[(HOST_SURFACE, "/loopx")] == "skipped_user_file"
    assert skill_path.read_text(encoding="utf-8") == "user-owned skill body\n"

    skill_path.write_text(
        "<!-- loopx-managed-slash-command:v1 command=/loopx surface=claude-skills -->\nold\n",
        encoding="utf-8",
    )
    payload = install_slash_commands(
        execute=True,
        surfaces=[HOST_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    statuses = {
        (item["surface"], item["command"]): item["status"]
        for item in payload["installed"]
    }
    assert statuses[(HOST_SURFACE, "/loopx")] == "updated"
    assert "user-owned skill body" not in skill_path.read_text(encoding="utf-8")

    retire = install_slash_commands(
        execute=True,
        uninstall=True,
        surfaces=[HOST_SURFACE],
        devin_home=str(tmp_path / "devin-home"),
    )
    assert not skill_path.exists()
    assert retire["ok"] is True


def test_agent_type_catalog_and_scheduler_binding() -> None:
    """A host with no scheduler binding falls through to the generic default and
    the loop it actually runs stops being visible to the control plane."""
    catalog = build_agent_type_catalog()
    entry = next(
        item
        for item in catalog["canonical_agent_types"]
        if item["agent_type"] == HOST_SURFACE
    )
    assert entry["display_name"] == "Devin CLI"
    assert entry["host_loop"]
    assert "gated" not in entry["host_loop"].lower()
    assert "advisory" in entry["host_loop"].lower()
    # The bare product name is what a user types.
    assert "devin" in entry["accepted_inputs"]
    assert normalize_agent_type("devin") == HOST_SURFACE
    assert normalize_agent_type("devin-cli") == HOST_SURFACE
    assert normalize_agent_type("Devin CLI") == HOST_SURFACE
    assert scheduler_command_binding_for_agent_type(HOST_SURFACE) == {
        "runtime_profile": "generic_cli"
    }


def test_activation_binds_native_loop_with_advisory_quota_entry() -> None:
    """Devin CLI owns a native loop primitive (`/loop <prompt>`, whose host-side
    loop re-runs the prompt and auto-reviews the diff; requires clean git state
    to start) and a lifecycle-hook seam. The packet has to state exactly that
    capability envelope: bind the objective via `/loop`, state advisory quota
    pacing without claiming a host hook intercepts iterations, and admit the
    loop dies with the session — an overstated capability here is what makes an
    agent claim autonomous setup it cannot deliver."""
    packet = build_host_loop_activation_packet(
        agent_type=HOST_SURFACE,
        goal_id="surface-goal",
        agent_id="probe-agent",
        registered_agents=["probe-agent"],
    )
    assert packet["activation_method"] == "bind_native_loop_with_advisory_quota_entry"
    mutation = packet["host_mutation"]
    assert mutation["cli_can_mutate_directly"] is False
    # The native primitive is real and must be named, not denied.
    assert mutation["host_loop_primitive"] == "devin-cli-/loop-diff-review-loop"
    assert mutation["loop_driver"] == "devin_cli_native_loop"
    # The quota claim must be honest: advisory guidance, no installed hook.
    assert mutation["quota_gate_enforcement"] == "advisory_only"
    assert mutation["native_loop_command"] == DEVIN_CLI_LOOP_COMMAND
    assert mutation["host_session_id_env"] == DEVIN_CLI_SESSION_ID_ENV
    # The hook seam exists but LoopX installs none; recording the triggers must
    # not be read as a claim of enforcement.
    assert "PreToolUse" in mutation["host_hook_triggers"]
    assert "Stop" in mutation["host_hook_triggers"]
    # The loop dies with the CLI session; the gate text must say so instead of
    # promising unattended heartbeat support.
    gate = mutation["missing_host_tool_gate"]
    assert "only" in gate
    assert "alive" in gate
    assert "daemon" in gate
    assert "advisory" in gate
    assert "installs no Devin hook" in gate

    steps = " ".join(packet["activation_steps"])
    assert DEVIN_CLI_LOOP_COMMAND in steps
    assert "quota should-run" in steps
    assert "clean git state" in steps
    assert "no host scheduler to fall back on" not in steps
    # Every copyable command in the packet must match the contracted shape.
    # Prose elsewhere cannot repair a command a reader has already executed.

    assert packet["setup_command"] == _surface_install_command(
        HOST_SURFACE, "loopx", "."
    )
    assert "quota should-run" in _start_instruction(HOST_SURFACE)
    assert DEVIN_CLI_LOOP_COMMAND in _start_instruction(HOST_SURFACE)
    assert (
        packet["entry_command_hint"]
        == f"the LoopX skill installed in {SKILLS_ROOT_LABEL}"
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


def test_native_loop_facts_match_the_documented_host() -> None:
    """The host-facts constants are the single source the activation packet,
    README and PR narrative cite, so they must stay pinned to what the host
    itself contracts (verified against the published Devin CLI docs,
    v3000.10.21)."""
    assert DEVIN_CLI_LOOP_COMMAND == "/loop"
    assert DEVIN_CLI_SESSION_ID_ENV == "DEVIN_SESSION_ID"
    assert set(DEVIN_CLI_HOOK_TRIGGERS) == {
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
        "UserPromptSubmit",
        "Stop",
        "PostCompaction",
        "SessionStart",
        "SessionEnd",
    }
    facts = " ".join(DEVIN_CLI_NATIVE_LOOP_FACTS)
    assert "/loop" in facts
    assert "diff" in facts
    assert "clean git state" in facts
    assert "session" in facts
    assert "daemon" in facts
    assert "hooks" in facts
    assert "Stop" in facts
    assert "PreToolUse" in facts
    assert "skills" in facts
    assert "SKILL.md" in facts
