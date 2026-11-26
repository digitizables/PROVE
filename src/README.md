# src

`prove` runs one ready intent and writes the worker result back onto the place file. Commands, exit codes, and the actions it implements are in `../docs/runtime.md`.

```powershell
$env:PYTHONPATH = "src;..\roblox-studio-adapter\src"
python -m prove status graph/places/example.place.json
```

MCP framing, retries, and datamodel selection stay in the adapter. The contracts are in `../protocols`.
