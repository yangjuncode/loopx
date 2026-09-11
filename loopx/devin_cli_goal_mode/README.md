# Devin CLI goal mode

LoopX adapter for the [Devin CLI](https://devin.ai/support) (binary `devin`)
— Cognition's terminal coding agent. Devin CLI ships one half of a goal-mode
host natively: a `/loop` diff-review primitive, so LoopX binds the objective
to the host's own loop instead of pretending the agent merely drives itself.

## Native loop primitive (verified against the published docs, v3000.10.21)

`/loop <prompt>` — built-in command, "Run a prompt then auto-review the diff
in a loop (requires clean git state to start)." The host re-runs the prompt
and auto-reviews the diff in a loop while the session is alive. Live evidence
from the published `essential-commands` reference:

- `/loop <prompt>` is listed under the "Automation" slash-command group.
- The loop requires clean git state to start, so commit or stash unrelated
  changes before binding the objective.
- The mechanism is built into the binary (the host owns the loop iteration,
  not the model driving itself).

## Native hook seam (verified against the published docs, v3000.10.21)

Devin CLI ships a real lifecycle-hook seam. `PreToolUse`, `PostToolUse`,
`PermissionRequest`, `UserPromptSubmit`, `Stop`, `PostCompaction`,
`SessionStart`, and `SessionEnd` fire on tool and session events. `Stop`
can block the agent from stopping (exit code 2 or `decision: block`), and
`PreToolUse` can block or rewrite a tool call. LoopX installs no hook today,
so quota pacing stays advisory; the seam is recorded here so the honest claim
and the future binding point stay in one place.

## What this surface is

Devin CLI discovers global skills from `~/.config/devin/skills/<name>/SKILL.md`
(following XDG conventions) and project skills from
`.devin/skills/<name>/SKILL.md`. LoopX reaches a `devin` session through the
generated `/loopx` skill facade, and the activation binds the objective with
the native `/loop <task_body>` command.

Two honest limits, stated in the activation packet:

- **Quota pacing is advisory.** LoopX installs no Devin hook that intercepts
  native loop iterations, so `quota should-run` entry is facade guidance the
  agent is instructed to follow — not a host-enforced gate. Devin CLI will
  continue natively without it.
- **Everything lives and dies with the session.** The `/loop` loop fires only
  while the CLI session is alive — there is no cross-session daemon — so it
  arms a live session's bounded segments, not an unattended host loop.

## Install

```bash
loopx slash-commands --install --surface devin-cli
```

Writes the managed LoopX skill facades (`loopx/SKILL.md`,
`loopx-global-summary/SKILL.md`, …) into `~/.config/devin/skills/<name>/SKILL.md`
— the documented Devin CLI global layout. The host documents no dedicated
home override, but `XDG_CONFIG_HOME` relocates the whole `~/.config` tree, so
LoopX resolves it the same way the host does. Managed files carry the
`loopx-managed-slash-command` marker and are refreshed by rerunning the
installer; user-owned files are never overwritten.

## Use

From a Devin CLI session in a connected project, invoke the `loopx` skill
(or type `/loopx <complex task>`). The facade instructs the agent to run:

```bash
loopx start-goal --guided --project . --slash-command-arguments="<task>" --host-surface devin-cli
```

After todo writeback, bind the generated heartbeat task body with the native
`/loop <task_body>` (the loop requires clean git state to start, so commit or
stash unrelated changes first), start every following turn (and every loop
iteration) with `quota should-run` (advisory guidance; LoopX does not intercept
native host loop iterations), and re-arm one further bounded `/loop`
invocation only when quota allows more work.

## Layout

- `__init__.py` — host facts: install surface id, skills root resolution,
  activation extras (advisory quota pacing and continuation boundaries), and
  the native loop + hook primitives the activation cites.
