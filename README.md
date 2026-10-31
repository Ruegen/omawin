# Omawin

Pick how apps open on Hyprland: tiled, floating, centered, or fullscreen.

Made for [Omarchy](https://omarchy.org).

Omawin lists the apps on your machine, with icon and name. Each row shows how that app is opening **right now** (a live window, your rule, or the desktop default). Change the radios to force the next launch.

Steam games stay out of a `steam` search. Search the game name to find those.

## Keys

- `j` / `k` or arrows — move
- `1`–`5` — Default, Tiled, Float, Center, Full
- `/` — search
- `q` or Escape — quit

## Run

Needs GTK 4 and the system Python (`/usr/bin/python3`).

```bash
install -Dm755 bin/omawin ~/.local/bin/omawin
install -Dm644 packaging/omawin.desktop ~/.local/share/applications/omawin.desktop
```

Then run `omawin`.

Load the generated rules from Hyprland after Omarchy’s defaults:

```lua
dofile(os.getenv("HOME") .. "/apps/omawin/packaging/hyprland-omawin.lua")
dofile(os.getenv("HOME") .. "/.config/hypr/omawin-rules.lua")
```

Your choices are stored in `~/.config/omawin/rules.json` and written to `~/.config/hypr/omawin-rules.lua`.
