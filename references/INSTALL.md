# Installation

> The canonical install guide is in the [main README](../README.md#install).
> This page is a quick reference for OS-specific steps.

## macOS

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install 'meeting-intelligence[local]'
```

## Windows

```powershell
winget install Gyan.FFmpeg
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install 'meeting-intelligence[local]'
```

## Linux

```bash
sudo apt-get install -y ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install 'meeting-intelligence[local]'
```

## CUDA (GPU acceleration)

```bash
pip install 'meeting-intelligence[gpu]'
meeting transcribe meeting.mp4 --device cuda
```

## Web dashboard

```bash
pip install 'meeting-intelligence[web]'
meeting serve
```

## MCP server (Agent Plugins)

```bash
pip install 'meeting-intelligence[mcp]'
python -m meeting_intelligence.mcp_server
```

## Everything

```bash
pip install 'meeting-intelligence[all]'
```

## From source (development)

```bash
git clone https://github.com/NikolayGusev-astra/hermes-meeting.git
cd hermes-meeting
pip install -e '.[dev]'
pytest -q
```
