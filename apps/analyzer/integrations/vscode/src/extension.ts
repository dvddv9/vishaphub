import * as vscode from "vscode";
import { spawn, ChildProcess } from "node:child_process";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

type Finding = { file?: string; line?: number; severity?: string; title?: string; id?: string; cwe?: string };
type ScanResult = { findings?: Finding[]; files_scanned?: number; files_skipped?: Array<{ file: string; reason: string }> };

const extensions = new Set([".py", ".pyw", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".c", ".h",
  ".cc", ".cpp", ".hpp", ".go", ".php", ".rb", ".rs", ".cs", ".kt", ".kts", ".swift", ".scala", ".sc",
  ".tf", ".tfvars", ".yaml", ".yml", ".sh", ".bash", ".sql", ".hcl"]);

export function activate(context: vscode.ExtensionContext): void {
  const diagnostics = vscode.languages.createDiagnosticCollection("vishap");
  const output = vscode.window.createOutputChannel("Vishap Security");
  const timers = new Map<string, NodeJS.Timeout>();
  const processes = new Map<string, ChildProcess>();

  const runScan = async (folder: vscode.WorkspaceFolder): Promise<void> => {
    const root = folder.uri.fsPath;
    const previous = processes.get(root);
    previous?.kill();
    const temporary = path.join(os.tmpdir(), `vishap-${process.pid}-${Date.now()}.json`);
    const executable = vscode.workspace.getConfiguration("vishap", folder.uri).get<string>("executable", "vishap");
    output.appendLine(`Scanning ${root}`);
    await new Promise<void>((resolve) => {
      const child = spawn(executable, ["scan", root, "--json", temporary], { cwd: root, shell: false, windowsHide: true });
      processes.set(root, child);
      let stderr = "";
      child.stderr?.on("data", (data: Buffer) => { stderr += data.toString("utf8"); });
      child.on("error", (error) => {
        output.appendLine(`Could not start ${executable}: ${error.message}`);
        vscode.window.showErrorMessage(`Vishap CLI could not start: ${error.message}`);
        resolve();
      });
      child.on("close", async (code) => {
        if (processes.get(root) === child) processes.delete(root);
        try {
          if (code !== 0) throw new Error(stderr.trim() || `scanner exited with code ${code}`);
          const report = JSON.parse(await fs.readFile(temporary, "utf8")) as ScanResult;
          const grouped = new Map<string, vscode.Diagnostic[]>();
          const max = vscode.workspace.getConfiguration("vishap", folder.uri).get<number>("maxFindings", 500);
          for (const finding of (report.findings || []).slice(0, max)) {
            if (!finding.file) continue;
            const file = path.resolve(root, finding.file);
            const relative = path.relative(root, file);
            if (relative.startsWith("..") || path.isAbsolute(relative)) continue;
            const line = Math.max(0, Number(finding.line || 1) - 1);
            const severity = String(finding.severity || "low").toLowerCase();
            const kind = severity === "critical" || severity === "high" ? vscode.DiagnosticSeverity.Error
              : severity === "medium" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information;
            const message = `${finding.title || finding.id || "Security finding"}${finding.cwe ? ` (${finding.cwe})` : ""}`;
            const diagnostic = new vscode.Diagnostic(new vscode.Range(line, 0, line, 0), message, kind);
            diagnostic.source = "Vishap";
            diagnostic.code = finding.id;
            const rows = grouped.get(file) || [];
            rows.push(diagnostic);
            grouped.set(file, rows);
          }
          diagnostics.clear();
          for (const [file, rows] of grouped) diagnostics.set(vscode.Uri.file(file), rows);
          output.appendLine(`${report.files_scanned || 0} files scanned; ${(report.findings || []).length} finding(s)`);
          const skipped = report.files_skipped || [];
          if (skipped.length) output.appendLine(`${skipped.length} file(s) skipped; see the JSON report for details.`);
          vscode.window.setStatusBarMessage(`Vishap: ${(report.findings || []).length} finding(s)`, 5000);
        } catch (error) {
          output.appendLine(`Scan failed: ${String(error)}`);
          vscode.window.showErrorMessage(`Vishap scan failed: ${String(error)}`);
        } finally {
          await fs.rm(temporary, { force: true }).catch(() => undefined);
          resolve();
        }
      });
    });
  };

  const schedule = (document: vscode.TextDocument): void => {
    if (!vscode.workspace.getConfiguration("vishap").get<boolean>("scanOnSave", true)) return;
    const folder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (!folder || !extensions.has(path.extname(document.uri.fsPath).toLowerCase())) return;
    const root = folder.uri.fsPath;
    const old = timers.get(root);
    if (old) clearTimeout(old);
    timers.set(root, setTimeout(() => {
      timers.delete(root);
      void runScan(folder);
    }, 1200));
  };

  context.subscriptions.push(diagnostics, output,
    vscode.commands.registerCommand("vishap.scanWorkspace", async () => {
      const folders = vscode.workspace.workspaceFolders || [];
      if (!folders.length) return;
      for (const folder of folders) await runScan(folder);
    }),
    vscode.workspace.onDidSaveTextDocument(schedule),
    { dispose: () => { for (const timer of timers.values()) clearTimeout(timer); for (const child of processes.values()) child.kill(); } });
}

export function deactivate(): void { /* subscriptions clean up state */ }
