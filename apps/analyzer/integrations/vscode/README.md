# Vishap Security Scan for VS Code

The extension runs the installed `vishap` CLI locally and publishes repository-scan
findings as editor diagnostics. Source files stay on the machine.

## Install from source

1. Install the analyzer package and make `vishap` available on `PATH`.
2. In this directory, run `npm install` and `npm run compile`.
3. Package with `npx vsce package`, then install the generated `.vsix` from the editor's
   **Install from VSIX** command.
4. Run **Vishap: Scan Workspace**, or save a supported source file to trigger a scan.

Set `vishap.executable` to the full path of the CLI if it is not on `PATH`. Set
`vishap.scanOnSave` to `false` to disable automatic scans. The extension uses the same
bounded `vishap scan` repository command as CI; language depth and limits are documented
in `../../docs/sast-capabilities.md`.
