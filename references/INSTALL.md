# Installation

## macOS
```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Windows
```powershell
winget install ffmpeg
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Linux
```bash
sudo apt-get install -y ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## CUDA
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```
