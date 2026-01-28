# Toolbox

Modular terminal toolbox built with Textual.

## Run

```bash
python -m toolbox
```

Or install and run:

```bash
pip install -e .
toolbox
```

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
