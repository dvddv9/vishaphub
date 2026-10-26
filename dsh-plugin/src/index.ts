// my-dsh-plugin — Vishap Security Analysis tool for DeepSeek Harness.
//
// Sends the provided material to a locally running Vishap backend (FastAPI,
// default port 5001) and returns the analysis report.
//
// Configuration comes from the profile patch layer (cordis `config:`):
//
//   - insert:
//       - id: my-dsh-plugin
//         name: my-dsh-plugin
//         config:
//           baseUrl: http://127.0.0.1:5001
//           apiKeyEnv: CONVEYOR_API_KEY    # credential name, never the value
//           timeoutMs: 120000
//           retries: 2
//           maxBytes: 2097152
//           cacheTtlMs: 600000
//
// This plugin carries no credential. The X-API-Key value is resolved per call
// from the harness credential store (ctx.get('credentials')), then the
// environment; with neither set no header is sent. Nothing here throws at load
// time: a plugin that fails to activate can take the whole harness startup down.
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { closeSync, openSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

export const name = 'my-dsh-plugin'
export const inject = ['tools']

export interface Config {
  /** Backend base URL. Default: `$VISHAP_URL`, else http://127.0.0.1:5001 */
  baseUrl?: string
  /**
   * Name of the credential to send as `X-API-Key` — resolved through the
   * harness credential store, then the environment. This is a reference, never
   * the secret itself. Default `CONVEYOR_API_KEY`. When it resolves to nothing
   * no header is sent, which a loopback Vishap started with
   * `VISHAP_ALLOW_NO_KEY=1` accepts.
   */
  apiKeyEnv?: string
  /** Budget for one backend call, ms. Default 120000. */
  timeoutMs?: number
  /** Extra attempts after the first one. Default 2. */
  retries?: number
  /** Maximum material size, bytes. Default 2 MiB. */
  maxBytes?: number
  /** Local result cache TTL, ms. Default 10 minutes. */
  cacheTtlMs?: number
  /** Start the backend when `/health` does not answer. Default true. */
  autoStart?: boolean
  /**
   * Vishap checkout to start, used as the child's working directory. Default
   * `$VISHAP_HOME`. Required when `autoStart` is on and the backend is down.
   */
  startCwd?: string
  /** Explicit executable and arguments. Default `<startCwd>/.venv/.../python -m src.main`. */
  startCommand?: string[]
  /** How long to wait for `/health` after spawning, ms. Default 60000. */
  startTimeoutMs?: number
  /**
   * Replace a Vishap instance this plugin did not start: probe, identify it via
   * `/openapi.json`, stop it, then spawn a fresh one. Default true.
   */
  replaceRunning?: boolean
  /** Stop the backend this plugin started once the call finishes. Default true. */
  stopWhenDone?: boolean
}

interface ToolResult {
  analysis: string
  verdict: string
  cwe_ids: string[]
}

const FILENAME_RE = /^[\w.-]{1,64}$/
const sha256 = (s: string) => createHash('sha256').update(s).digest('hex')

export function apply(ctx: Context, config: Config = {}) {
  const baseUrl = (config.baseUrl ?? process.env.VISHAP_URL ?? 'http://127.0.0.1:5001').replace(/\/+$/, '')
  const timeoutMs = config.timeoutMs ?? 120_000
  const retries = Math.max(0, config.retries ?? 2)
  const maxBytes = config.maxBytes ?? 2 * 1024 * 1024
  const cacheTtlMs = config.cacheTtlMs ?? 10 * 60_000
  const cacheMax = 32

  const cache = new Map<string, { value: ToolResult; expires: number }>()

  const autoStart = config.autoStart ?? true
  const startTimeoutMs = config.startTimeoutMs ?? 60_000
  const replaceRunning = config.replaceRunning ?? true
  const stopWhenDone = config.stopWhenDone ?? true
  let starting: Promise<void> | undefined
  let owned: ChildProcess | undefined
  let activeCalls = 0

  /** `/health` is unauthenticated on the Vishap API, so it is a safe liveness probe. */
  async function probe(probeTimeoutMs: number): Promise<boolean> {
    try {
      const response = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(probeTimeoutMs) })
      return response.ok
    } catch {
      return false
    }
  }

  function logTail(logPath: string): string {
    try {
      return readFileSync(logPath, 'utf8').slice(-1200).trim()
    } catch {
      return ''
    }
  }

  function startPlan(): { command: string; args: string[]; cwd: string; logPath: string } {
    const cwd = config.startCwd ?? process.env.VISHAP_HOME
    if (cwd === undefined || cwd === '') {
      throw new Error(
        'vishap_analyze: the backend is down and no start directory is configured. ' +
        'Set `startCwd` for this plugin (the Vishap checkout) or export VISHAP_HOME.',
      )
    }
    const exe = process.platform === 'win32'
      ? join(cwd, '.venv', 'Scripts', 'python.exe')
      : join(cwd, '.venv', 'bin', 'python')
    const configured = config.startCommand
    return {
      command: configured?.[0] ?? exe,
      args: configured === undefined ? ['-m', 'src.main'] : configured.slice(1),
      cwd,
      logPath: join(cwd, '_dsh-backend.log'),
    }
  }

  async function spawnBackend(): Promise<void> {
    const { command, args, cwd, logPath } = startPlan()
    const log = openSync(logPath, 'a')
    const child = spawn(command, args, {
      cwd,
      stdio: ['ignore', log, log],
      windowsHide: true,
      env: { ...process.env },
    })
    closeSync(log)

    let exit: { code: number | null; error?: string } | undefined
    owned = child
    child.once('error', (error: Error) => { exit = { code: -1, error: error.message } })
    child.once('exit', (code: number | null) => {
      exit = { code }
      if (owned === child) owned = undefined
    })

    const deadline = Date.now() + startTimeoutMs
    while (Date.now() < deadline) {
      if (await probe(1000)) {
        console.log(`[my-dsh-plugin] started the Vishap backend (pid ${child.pid ?? '?'}) from ${cwd}`)
        return
      }
      if (exit !== undefined) {
        const tail = logTail(logPath)
        throw new Error(
          `vishap_analyze: the backend exited during startup (code ${exit.code}` +
          `${exit.error === undefined ? '' : `, ${exit.error}`}). ` +
          `Its output is in ${logPath}${tail === '' ? '' : `:\n${tail}`}`,
        )
      }
      await sleep(400)
    }
    throw new Error(
      `vishap_analyze: the backend did not answer /health within ${startTimeoutMs} ms. ` +
      `It may still be starting; see ${logPath}.`,
    )
  }

  function portOfBaseUrl(): number {
    try {
      const port = new URL(baseUrl).port
      return port === '' ? 80 : Number(port)
    } catch {
      return 0
    }
  }

  /** PIDs listening on one port, or an empty list when the port is free or unreadable. */
  function listeningPids(port: number): number[] {
    try {
      if (process.platform === 'win32') {
        const out = execFileSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8' })
        const pids = new Set<number>()
        for (const line of out.split(/\r?\n/)) {
          if (!line.includes('LISTENING')) continue
          const cols = line.trim().split(/\s+/)
          if (cols.length < 5 || cols[1]?.endsWith(`:${port}`) !== true) continue
          const pid = Number(cols[4])
          if (Number.isInteger(pid) && pid > 0) pids.add(pid)
        }
        return [...pids]
      }
      const out = execFileSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' })
      return out.split(/\s+/).map(Number).filter((pid) => Number.isInteger(pid) && pid > 0)
    } catch {
      return []
    }
  }

  /** Identify before killing: only a Vishap instance may be replaced. */
  async function isVishap(): Promise<boolean> {
    try {
      const response = await fetch(`${baseUrl}/openapi.json`, { signal: AbortSignal.timeout(2000) })
      if (!response.ok) return false
      return /vishap/i.test((await response.text()).slice(0, 4000))
    } catch {
      return false
    }
  }

  async function stopPids(pids: number[]): Promise<void> {
    for (const pid of pids) {
      try { process.kill(pid, 'SIGTERM') } catch { /* escalation below handles it */ }
    }
    const deadline = Date.now() + 8000
    while (Date.now() < deadline) {
      const alive = pids.some((pid) => {
        try { process.kill(pid, 0); return true } catch { return false }
      })
      if (!alive) return
      await sleep(200)
    }
    for (const pid of pids) {
      try { process.kill(pid, 'SIGKILL') } catch { /* already gone */ }
      if (process.platform === 'win32') {
        try { execFileSync('taskkill', ['/F', '/PID', String(pid)], { stdio: 'ignore' }) } catch { /* already gone */ }
      }
    }
  }

  /** Stop an instance this plugin did not start, then leave the port free. */
  async function replaceForeign(): Promise<void> {
    if (!(await isVishap())) {
      throw new Error(
        `vishap_analyze: ${baseUrl} answers /health but is not Vishap (no Vishap title in /openapi.json). ` +
        'Refusing to stop it; point baseUrl at the right port or set replaceRunning: false.',
      )
    }
    const pids = listeningPids(portOfBaseUrl())
    if (pids.length === 0) {
      throw new Error(`vishap_analyze: ${baseUrl} answers but its listening pid was not found.`)
    }
    console.log(`[my-dsh-plugin] stopping a Vishap instance it did not start (pid ${pids.join(', ')})`)
    await stopPids(pids)
    const deadline = Date.now() + 8000
    while (Date.now() < deadline) {
      if (!(await probe(500))) return
      await sleep(300)
    }
    throw new Error(`vishap_analyze: could not free ${baseUrl} after stopping pid ${pids.join(', ')}.`)
  }

  /** Stop the instance this plugin started, if any. */
  async function stopOwned(): Promise<void> {
    const child = owned
    if (child === undefined) return
    owned = undefined
    if (child.exitCode !== null || child.signalCode !== null) return
    const pid = child.pid
    try { child.kill('SIGTERM') } catch { /* ignore */ }
    const deadline = Date.now() + 8000
    while (Date.now() < deadline) {
      if (child.exitCode !== null || child.signalCode !== null) break
      await sleep(150)
    }
    if (child.exitCode === null && child.signalCode === null && pid !== undefined) {
      try { process.kill(pid, 'SIGKILL') } catch { /* already gone */ }
    }
    console.log(`[my-dsh-plugin] stopped the Vishap backend it started (pid ${pid ?? '?'})`)
  }

  async function ensureBackend(): Promise<void> {
    if (starting !== undefined) {
      await starting
      return
    }
    if (owned !== undefined && owned.exitCode === null) return
    if (await probe(1500)) {
      if (!replaceRunning) return
      // Someone else's instance is holding the port: stop it so ours can bind.
      await replaceForeign()
    }
    if (!autoStart) {
      throw new Error(`vishap_analyze: backend is not reachable at ${baseUrl} and autoStart is disabled.`)
    }
    if (starting === undefined) {
      starting = spawnBackend().finally(() => { starting = undefined })
    }
    await starting
  }

  async function resolveApiKey(): Promise<{ key?: string; source: 'credentials' | 'env' | 'none' }> {
    const ref = config.apiKeyEnv ?? 'CONVEYOR_API_KEY'

    // The harness credential store is the preferred source: the value lives
    // there, not in this plugin or in the profile patch. `ctx.get` reads a
    // service without declaring an inject dependency, so a composition without
    // a credential store still falls back to the environment.
    const getService = (ctx as unknown as { get?: (name: string) => unknown }).get
    const store = typeof getService === 'function'
      ? getService.call(ctx, 'credentials') as { resolve?: (name: string) => Promise<{ value?: unknown } | undefined> } | undefined
      : undefined
    if (store !== undefined && typeof store.resolve === 'function') {
      try {
        const hit = await store.resolve(ref)
        const value = typeof hit?.value === 'string' ? hit.value.trim() : ''
        if (value !== '') return { key: value, source: 'credentials' }
      } catch {
        // A broken store must not mask the environment fallback.
      }
    }

    const env = (process.env[ref] ?? '').trim()
    if (env !== '') return { key: env, source: 'env' }
    return { source: 'none' }
  }

  ctx.tools.register(defineTool({
    name: 'vishap_analyze',
    description: 'Analyze code, spec, logs, or config for security risks (SQLi, XSS, RCE) using a local Vishap backend.',
    // The harness deadline sits above our own so the tool can report a clean
    // timeout instead of being killed from outside.
    timeoutMs: timeoutMs + (autoStart ? startTimeoutMs : 0) + 15_000,

    parameters: {
      material: {
        type: 'string',
        required: true,
        description: 'The code, config, or log text to analyze.',
      },
      filename: {
        type: 'string',
        description: 'Optional filename for context (e.g., "app.py").',
      },
    },

    output: {
      schema: {
        type: 'object',
        properties: {
          analysis: { type: 'string', required: true, description: 'Markdown report from Vishap.' },
          verdict: { type: 'string', required: true, description: 'Vishap verdict (e.g., PASS, FAIL, ERROR).' },
          cwe_ids: { type: 'array', items: { type: 'string' }, required: true, description: 'List of detected CWE IDs.' },
        },
        additionalProperties: false,
      },
      render: (_args, value) => [
        { type: 'text', text: value.analysis },
        { type: 'text', text: `\n\n[VERDICT] ${value.verdict} | CWE: ${value.cwe_ids.join(', ') || 'none'}` },
      ],
    },

    async execute(args, exec) {
      const a = args as { material: string; filename?: string }
      const material = a.material

      if (typeof material !== 'string' || material.trim() === '') {
        throw new Error('vishap_analyze: material must be a non-empty string')
      }
      const bytes = Buffer.byteLength(material, 'utf8')
      if (bytes > maxBytes) {
        throw new Error(
          `vishap_analyze: material is ${bytes} bytes, limit is ${maxBytes}. ` +
          'Split the input or raise `maxBytes` in the plugin config.',
        )
      }

      const filename = a.filename ?? 'input.txt'
      if (!FILENAME_RE.test(filename)) {
        throw new Error('vishap_analyze: filename must match /^[\\w.-]{1,64}$/ — it is embedded in the analysis prompt')
      }

      const digest = sha256(material)
      const cacheKey = `${filename}:${digest}`
      const cached = cache.get(cacheKey)
      if (cached && cached.expires > Date.now()) return cached.value
      if (cached) cache.delete(cacheKey)

      const auth = await resolveApiKey()

      activeCalls += 1
      try {
        await ensureBackend()
        const deadline = AbortSignal.timeout(timeoutMs)
        const signal = exec?.signal ? AbortSignal.any([exec.signal, deadline]) : deadline

        let lastErr: unknown
        for (let attempt = 0; attempt <= retries; attempt++) {
          try {
            const response = await fetch(`${baseUrl}/analyze`, {
              method: 'POST',
              signal,
              headers: {
                'Content-Type': 'application/json',
                ...(auth.key === undefined ? {} : { 'X-API-Key': auth.key }),
              },
              body: JSON.stringify({
                material,
                filename,
                // Content-derived: the same input maps to the same backend session,
                // which keeps the server-side dedup cache effective.
                session_id: `dsh-${digest.slice(0, 16)}`,
              }),
            })

            if (!response.ok) {
              const body = (await response.text()).slice(0, 200)
              // 4xx is our fault (bad key, bad payload, too large): retrying cannot help.
              if (response.status < 500) {
                const hint = auth.key === undefined && (response.status === 401 || response.status === 403)
                  ? ` No X-API-Key was sent: store one under "${config.apiKeyEnv ?? 'CONVEYOR_API_KEY'}" in the ` +
                    'harness credential store, or run Vishap on loopback with VISHAP_ALLOW_NO_KEY=1.'
                  : ''
                throw new Error(`Vishap rejected the request (HTTP ${response.status}): ${body}${hint}`)
              }
              lastErr = new Error(`Vishap HTTP ${response.status}: ${body}`)
            } else {
              const data = await response.json() as {
                final_markdown?: unknown
                verdict?: unknown
                audit?: { cwe_ids?: unknown }
              }
              const value: ToolResult = {
                analysis: typeof data.final_markdown === 'string' && data.final_markdown
                  ? data.final_markdown
                  : 'No report generated.',
                verdict: typeof data.verdict === 'string' && data.verdict ? data.verdict : 'UNKNOWN',
                cwe_ids: Array.isArray(data.audit?.cwe_ids)
                  ? data.audit.cwe_ids.filter((x): x is string => typeof x === 'string')
                  : [],
              }
              cache.set(cacheKey, { value, expires: Date.now() + cacheTtlMs })
              while (cache.size > cacheMax) {
                const oldest = cache.keys().next().value
                if (oldest === undefined) break
                cache.delete(oldest)
              }
              return value
            }
          } catch (error) {
            // A 4xx thrown above is final; everything else may be transient.
            if (error instanceof Error && error.message.startsWith('Vishap rejected the request')) throw error
            if (exec?.signal?.aborted) throw new Error('vishap_analyze: cancelled by the caller')
            if (deadline.aborted) {
              throw new Error(
                `vishap_analyze: no answer from ${baseUrl} within ${timeoutMs} ms. ` +
                'The analysis may still be running in the backend; check its log.',
              )
            }
            lastErr = error
          }

          if (attempt < retries) {
            try {
              await sleep(250 * 2 ** attempt, undefined, { signal })
            } catch {
              break // aborted during backoff
            }
          }
        }

        const cause = lastErr instanceof Error ? lastErr : new Error(String(lastErr))
        throw new Error(
          `vishap_analyze: backend unavailable at ${baseUrl} after ${retries + 1} attempt(s) ` +
          `(X-API-Key source: ${auth.source}): ${cause.message}. ` +
          'Is Vishap running? See the plugin README for the manual start command.',
          { cause },
        )
      } finally {
        activeCalls -= 1
        // The last call in flight owns the shutdown, so a concurrent call never
        // loses its backend mid-analysis.
        if (stopWhenDone && activeCalls === 0) await stopOwned()
      }
    },
  }))

  console.log(`[my-dsh-plugin] vishap_analyze → ${baseUrl} (X-API-Key resolved per call from "${config.apiKeyEnv ?? 'CONVEYOR_API_KEY'}", timeout ${timeoutMs} ms)`)
}
