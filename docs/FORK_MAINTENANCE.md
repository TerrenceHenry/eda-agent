# Maintaining this fork

This fork removes sponsorship UI from the Altium bridge and disables
background update checks by default. Explicit manual checks and an explicit
background-check opt-in remain available.

## Required check

The trusted **Fork policies (AppVeyor)** check is required for `main`.
AppVeyor runs the fork policy test on Windows using the build settings
for this repository. Keep the required check name and provider stable.

The independent `tests/test_fork_policies.py` checks all Altium Pascal and
form sources for sponsorship UI and heart icons, including the removed MDL2
heart under a renamed control. It calls the actual updater startup hook
with the setting absent and disabled, failing before any thread, process
or network request can start. It does not inherit a forced-disabled CI
setting that could hide a change to the default.

Run it locally without installing dependencies:

```powershell
python -S -m unittest tests.test_fork_policies -v
```

The same guard is included in `python scripts/check.py`. Keep it separate
from upstream's sponsorship and updater tests when resolving merge conflicts.
The main-branch protection requires it to pass against the current base and
applies to administrators too. Force pushes and branch deletion are disabled.

## Updating from upstream

1. Prepare an upstream merge on a working branch in a separate worktree.
   Deploy from the verified wheel and its matching bundled scripts.
2. Preserve the fork policies, their workflow and tests when resolving
   conflicts. Keep `EDA_AGENT_UPDATE_CHECK=0` in the MCP configuration.
3. Run the fork guard and the project's other required checks. Push the
   working branch and wait for **Fork policies (AppVeyor)** to pass before merging.
4. After review and native verification, install the wheel in a dedicated
   environment. Deploy the Altium scripts, restart the bridge and reconnect Codex.
5. Verify the live MCP version, script location, unit hashes and updater
   environment. A successful source check alone is not live verification.

The guard detects the prohibited UI and the updater's startup behavior; it
is not a general audit of arbitrary future code. Intentionally changing or
removing these policies requires an explicit decision by the fork owner.
