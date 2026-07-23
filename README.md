# Meeting Intelligence

Meeting Intelligence turns audio, video, and supported media URLs into timestamped transcripts and grounded meeting protocols. It runs locally by default. Cloud LLMs require explicit opt-in.

## Requirements

- Python 3.10 or newer
- `ffmpeg` installed and available on `PATH`
- At least 8 GB RAM
- An LLM backend: LM Studio, Ollama, llama.cpp, or an explicitly enabled cloud API
- Optional: an NVIDIA CUDA GPU for faster transcription

Install `ffmpeg` before using transcription:

| Platform | Install command |
| --- | --- |
| Windows | `winget install Gyan.FFmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt update && sudo apt install ffmpeg` |
| macOS | `brew install ffmpeg` |

## Install

Create and activate a virtual environment, then select the extra that matches your use case.

### Windows

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install meeting-intelligence[local]
```

### Linux

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install 'meeting-intelligence[local]'
```

### macOS

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install 'meeting-intelligence[local]'
```

### Optional dependency groups

| Extra | Use it for |
| --- | --- |
| `local` | Local LLM backends. Core dependencies already provide this path. |
| `cloud` | Explicit cloud LLM use. Set `MEETING_ALLOW_CLOUD=true` or pass `--allow-cloud`. |
| `gpu` | NVIDIA CUDA runtime support on Windows and Linux. |
| `diarization` | Speaker diarization with `pyannote.audio`. |
| `url` | Media URL downloads with `yt-dlp`. |
| `all` | Every optional capability. |
| `dev` | Test, lint, and build tools. |

For a source checkout, install with `pip install -e '.[dev]'`.

## GPU setup

GPU acceleration is optional. Install a compatible NVIDIA driver and CUDA 12 runtime, then install the GPU extra:

```bash
pip install 'meeting-intelligence[gpu]'
```

On Windows and Linux, the package installs `nvidia-cublas-cu12`. Run `meeting transcribe ... --device cuda` to request CUDA. The CLI falls back to CPU if a usable GPU is unavailable. macOS uses CPU transcription.

## Quick start

```bash
pip install 'meeting-intelligence[local]'
meeting transcribe /path/to/meeting.mp4 --model small --language en --device cpu
meeting protocol /path/to/meeting.transcript.txt --model qwen2.5-7b-instruct
```

Configure one LLM backend before translating or generating a protocol:

```bash
# LM Studio
export MEETING_LLM_BASE_URL=http://localhost:1234/v1
export MEETING_LLM_API_KEY=lm-studio
export MEETING_LLM_MODEL=qwen2.5-7b-instruct

# Ollama
# export MEETING_LLM_BASE_URL=http://localhost:11434/v1
# export MEETING_LLM_API_KEY=ollama
# export MEETING_LLM_MODEL=llama3.1
```

In PowerShell, replace `export NAME=value` with `$env:NAME = "value"`.

Use a cloud endpoint only after opting in:

```bash
export MEETING_ALLOW_CLOUD=true
export MEETING_LLM_BASE_URL=https://api.openai.com/v1
export MEETING_LLM_API_KEY="$OPENAI_API_KEY"
export MEETING_LLM_MODEL=gpt-4o-mini
meeting translate /path/to/meeting.transcript.txt --target-lang ru --allow-cloud
```

## CLI

```bash
meeting transcribe SOURCE
meeting translate TRANSCRIPT --target-lang ru --allow-cloud
meeting protocol TRANSCRIPT --model qwen2.5-7b-instruct
meeting process SOURCE --stt-model small --llm-model qwen2.5-7b-instruct --language en --target-lang ru --docx
```

`SOURCE` may be a local audio/video file or, with the `url` extra installed, a supported media URL. You can also run `python -m meeting_intelligence`.

## Hermes plugin

Register the plugin in Hermes configuration:

```yaml
plugins:
  enabled:
    - meeting-intelligence
```

Available tools: `meeting_transcribe`, `meeting_translate`, `meeting_agent_transcript`, `meeting_protocol`, and `meeting_process`.

## Safety

- External endpoints are blocked unless `--allow-cloud` is supplied.
- Every decision and assignment needs a transcript-grounded `source_quote`.
- The service does not log secrets and writes audit metadata for each run.

## Release install smoke test

Run this in a clean virtual environment after publishing. It installs every extra, imports the package, and verifies the release version:

```bash
pip install 'meeting-intelligence[all]' && python -c "import meeting_intelligence; assert meeting_intelligence.__version__ == '0.7.0'; print(meeting_intelligence.__version__)"
```

## Development checks

```bash
pytest -q
ruff check .
```

## License

MIT
