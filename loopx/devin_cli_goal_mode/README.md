# Devin CLI goal mode

LoopX adapter for Devin CLI (binary `devin`) — a terminal coding agent with
skills, rules, hooks, MCP, and a native same-session goal loop.

## Native goal primitive

`/goal <objective>` — the built-in command as the host contracts it. The host
keeps the session working the objective across turns, continuing automatically
each time a turn ends, until it reports the goal complete or blocked.

- A goal run pauses itself after 50 turns. `/goal` alone shows its status,
  `/goal resume` continues after an interrupt, and `/goal clear` drops it.
- The primitive lives in the local interactive session; a one-shot prompt
  invocation carries no goal loop, so LoopX binds the live session instead of
  spawning host processes per turn.

## What this surface is

Devin CLI discovers global skills from
`$XDG_CONFIG_HOME/devin/skills/<name>/SKILL.md` (`~/.config/devin/skills` when
`XDG_CONFIG_HOME` is unset) and workspace skills from `.devin/skills/`; every
discovered skill is invocable as a `/<skill-name>` slash command. LoopX reaches
a Devin CLI session through the generated `/loopx` skill facade, and the
activation binds the objective with the native `/goal <task_body>`.

Honest limits, stated in the activation packet:

- **Quota pacing is advisory.** No LoopX hook intercepts a native goal
  continuation, so `quota should-run` entry is facade guidance the agent is
  instructed to follow — not a host-enforced gate.
- **LoopX cannot drive the TUI.** The CLI cannot type, resume, or clear a goal
  inside a running session on the user's behalf; the user or the host's own
  command path sets `/goal <task_body>`.

## Chat / ACP

Devin CLI also serves an ACP agent (`devin acp`), so `loopx dashboard` and
`loopx chat` list **Devin CLI** as a built-in Agent. It reuses
`loopx.chat_acp.ACPStdioAdapter` rather than a second transport, and the
adapter persists the returned ACP session id for resume.

The launch argv is `devin --permission-mode dangerous acp`: the global flag
must precede the subcommand, and `dangerous` is the host's maximum (Bypass
Permissions) mode. Both entry points — the interactive goal session and the
ACP agent — run under that one pin because this deployment is a
user-authorized controlled environment: the host applies tool calls without
prompting, so LoopX never sees an approval request to cancel. The capability
row honestly scopes to `workspace_write`: a maximum-permission host is not a
LoopX sandbox.

## Install

```bash
loopx slash-commands --install --surface devin
```

Writes the managed LoopX skill facades into `$XDG_CONFIG_HOME/devin/skills`
(default `~/.config/devin/skills`) using the per-skill directory layout.
Managed files carry the `loopx-managed-slash-command` marker and are refreshed
by rerunning the installer; user-owned files are never overwritten.

## Use

Start the session with `devin --permission-mode dangerous` — the same
user-authorized maximum-permission entry the ACP agent carries — then, in a
connected project, run `/loopx <complex task>`. The facade instructs the agent
to run:

```bash
loopx start-goal --guided --project . --slash-command-arguments="<task>" --host-surface devin-cli
```

After todo writeback, set the native `/goal <task_body>` in the same session,
start every turn and native goal continuation with `quota should-run`
(advisory guidance; LoopX does not intercept native host turns), and settle
LoopX writeback when the goal reports complete or blocked.

## Layout

- `__init__.py` — host facts: install surface id, the XDG skills root
  resolution, the agent-type catalog entry, and the activation extras (native
  goal command, resume/clear commands, 50-turn cap, advisory quota boundary).
