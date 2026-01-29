# Toolbox

Modular terminal toolbox built with Textual.

## Install (GitHub)

```bash
git clone git@github.com:<you>/<repo>.git
cd <repo>
./install.sh
```

## Run

```bash
python -m toolbox
./run.sh
toolbox
```

## Update

Use the Settings tool inside the app to check for updates and pull the latest code.
You can also update manually:

```bash
git pull --ff-only
./install.sh
```

## Available tools

- Audio Converter
- Audio Distance
- MaxGain
- Stereo Merger
- OSC Sender/Receiver
- TCP Sender/Receiver
- Network Info
- YouTube Downloader

## Add a tool

Create a module in `src/toolbox/tools/` and expose a `TOOL` variable:

```python
from toolbox.tools.base import Tool

TOOL = Tool(
    name="My Tool",
    description="What it does.",
)
```

## Audio converter notes

The audio converter uses `pydub` and requires `ffmpeg` on your system.
