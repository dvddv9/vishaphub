# Running VishapHub yourself

Three ways in, one program. Pick by who will use it.

| You are | Use | Code runs |
|---|---|---|
| one person, Docker installed | `selfhost/install.sh` / `install.ps1` | inside the hub container |
| a developer, Python 3.11+ | `selfhost/install-pipx.sh` / `.ps1`, then `vishap-hub init` | on your machine, or in a Docker worker |
| a Windows user, no tools | `VishapHub-Setup.exe` (built by `selfhost/windows/build.ps1`) | on your machine |

## pipx

```
selfhost/install-pipx.sh        # Windows: selfhost\install-pipx.ps1
vishap-hub init                 # model, privacy, how code runs -> ~/.vishaphub/config.env
vishap-hub doctor               # what this installation will do; exit 1 if something it needs is missing
vishap-hub serve                # http://127.0.0.1:8080, this machine only
```

A variable already in the environment wins over the settings file.

## Windows installer

`selfhost\windows\build.ps1` makes `VishapHub-Setup.exe` (needs Inno Setup 6). It installs for the current user, no
administrator rights, and carries its own Python, because the validator runs a deliverable's tests with
`sys.executable -m pytest`. It adds Start-menu entries "VishapHub" and "VishapHub settings" (the same questions as
`vishap-hub init`). Uninstalling removes the program and leaves `%USERPROFILE%\.vishaphub` (settings with the model key,
and the runs). The `.exe` is not code-signed, so Windows SmartScreen will warn on first run.

## Docker Compose

```
cd selfhost
./install.sh            # Windows: .\install.ps1
```

It asks four things (model, offline or not, how code is run, solo or team), writes `.env` (private to you),
builds the image and waits until `/health` answers. Open `http://127.0.0.1:8080`.

Day two: `./vishap.sh status | logs | stop | start | backup | restore <folder> | upgrade` (`vishap.ps1` on Windows).
A backup is a folder: `data.tar` (the runs), `db.dump` (team mode), `env.backup` (your `.env`, **with the model key and
passwords** - keep it private). `upgrade` backs up first, pulls, rebuilds and migrates.

## Which model

| `VISHAP_HUB_LLM_PROVIDER` | Needs | Notes |
|---|---|---|
| `anthropic` | `VISHAP_HUB_LLM_KEY` | Claude; default model `claude-sonnet-5-5` |
| `openai` | `VISHAP_HUB_LLM_URL`, `VISHAP_HUB_LLM_MODEL` (+ key for hosted ones) | OpenAI, OpenRouter, Ollama (`http://host.docker.internal:11434/v1`), LM Studio, vLLM. A key is required unless the URL is on this machine. |
| `none` | nothing | rules and validator only; model-written parts say they are off |

Tested against a fake local server speaking both dialects. **Not** tested against a live OpenAI or Ollama.

## Where nothing may leave

`VISHAP_HUB_OFFLINE=1` plus a local model: the process refuses connections outside this machine and the private
network, and the voice is off. This stops the hub's own connections. It is not a network firewall, and an offline
claim to a third party needs its own check.

## Running submitted code (`VISHAP_HUB_ISOLATION`)

You decide, because you know whose code it is.

- `host` - on this machine as the hub's user (in the Compose bundle: inside the container). For code you wrote or trust.
  The code can read the hub's environment, including the model key. Each result is marked `isolation: host, confirmed: false`.
- `auto` - a worker container or a network namespace when there is one, otherwise nothing is run.
- `docker` - only in a one-off worker container (`--network none --read-only`). Needs `VISHAP_HUB_WORKER_IMAGE` and the
  Docker CLI on the machine running the hub. The Compose bundle does not include it: giving a container the Docker
  socket would hand the host to whoever breaks the hub.

For code from strangers, run the hub on the host (pipx) with `docker`.
