#!/usr/bin/python3
"""Omawin: list installed apps and choose how they launch in Hyprland."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from omawin.detect import (
    MODE_LABELS,
    MODES,
    class_from_desktop,
    configured_modes,
    describe_state,
    include_app,
    live_clients,
    load_overrides,
    matches_query,
    reload_hyprland,
    save_overrides,
)

COLORS = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
LEGACY_COLORS = Path.home() / ".config/omarchy/current/theme/colors.toml"


def read_colors() -> dict[str, str]:
    path = COLORS if COLORS.is_file() else LEGACY_COLORS
    palette = {
        "background": "#1a1b26",
        "foreground": "#a9b1d6",
        "accent": "#7aa2f7",
        "selection": "#292e42",
        "muted": "#414868",
    }
    if not path.is_file():
        return palette
    for line in path.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key in palette or key in ("background", "foreground", "accent", "selection", "muted"):
            palette[key] = value
    return palette


def css_for(palette: dict[str, str]) -> str:
    bg, fg, accent, sel, muted = (
        palette["background"],
        palette["foreground"],
        palette["accent"],
        palette["selection"],
        palette["muted"],
    )
    return f"""
        window {{
            background: {bg};
            color: {fg};
        }}
        entry, list, row {{
            background: {bg};
            color: {fg};
            border-radius: 0;
        }}
        entry {{
            border: 2px solid {muted};
            padding: 6px 8px;
            caret-color: {accent};
        }}
        entry:focus {{
            border-color: {accent};
        }}
        row {{
            min-height: 52px;
            padding: 6px 10px;
            border: 2px solid transparent;
        }}
        row:selected, row:focus {{
            border-color: {accent};
            background: {sel};
        }}
        checkbutton {{
            padding: 0 6px;
            min-height: 0;
            font-size: 12px;
            color: {fg};
            border: none;
            box-shadow: none;
            outline: none;
        }}
        checkbutton:focus {{
            outline: none;
            box-shadow: none;
            border: none;
        }}
        checkbutton:focus radio {{
            box-shadow: 0 0 0 2px {accent};
        }}
        checkbutton radio {{
            min-width: 14px;
            min-height: 14px;
            border: 2px solid {accent};
            border-radius: 999px;
            background: transparent;
            box-shadow: none;
        }}
        checkbutton radio:checked {{
            background: {accent};
        }}
        .muted {{
            color: {muted};
        }}
        header {{
            padding: 10px 12px 6px 12px;
        }}
    """


class AppRow(Gtk.ListBoxRow):
    def __init__(self, info: Gio.AppInfo, wm_class: str, mode: str, source: str, override: str):
        super().__init__()
        self.info = info
        self.wm_class = wm_class
        self.mode = mode
        self.source = source
        self.override = override or "default"
        self.set_focusable(True)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon = Gtk.Image(pixel_size=28)
        gicon = info.get_icon()
        if gicon:
            icon.set_from_gicon(gicon)
        else:
            icon.set_from_icon_name("application-x-executable")
        box.append(icon)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text.set_hexpand(True)
        name = Gtk.Label(label=info.get_name() or info.get_id() or "App", xalign=0)
        status = Gtk.Label(
            label=f"{MODE_LABELS.get(mode, mode)} · {source}",
            xalign=0,
        )
        status.add_css_class("muted")
        status.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(name)
        text.append(status)
        box.append(text)

        radios = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.radios = {}
        self._setting = False
        group = None
        for key in MODES:
            radio = Gtk.CheckButton(label=MODE_LABELS[key])
            if group is not None:
                radio.set_group(group)
            else:
                group = radio
            radio.connect("toggled", self._on_radio, key)
            radios.append(radio)
            self.radios[key] = radio
        self._paint_radios()
        box.append(radios)
        self.set_child(box)

    def _paint_radios(self) -> None:
        chosen = self.override if self.override != "default" else "default"
        self._setting = True
        radio = self.radios.get(chosen)
        if radio:
            radio.set_active(True)
        self._setting = False

    def _on_radio(self, button, mode: str) -> None:
        if self._setting or not button.get_active():
            return
        window = self.get_root()
        if window:
            window.set_mode(self, mode)

    def matches(self, query: str) -> bool:
        return matches_query(self.info, self.wm_class, query)


class Omawin(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Omawin")
        self.set_default_size(980, 720)
        self.overrides = load_overrides()
        self.configured = configured_modes()
        self.clients = live_clients()
        self.rows: list[AppRow] = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.add_css_class("header")
        title = Gtk.Label(label="How apps open", xalign=0)
        hint = Gtk.Label(
            label="j/k move · 1–5 set mode · / search · q quit",
            xalign=0,
        )
        hint.add_css_class("muted")
        self.search = Gtk.Entry()
        self.search.set_placeholder_text("Search apps")
        self.search.connect("changed", self._on_search)
        header.append(title)
        header.append(hint)
        header.append(self.search)
        root.append(header)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_vexpand(True)
        scroll = Gtk.ScrolledWindow(child=self.listbox)
        scroll.set_vexpand(True)
        root.append(scroll)
        self.set_child(root)

        self._fill()
        self.apply_theme()
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        GLib.timeout_add_seconds(2, self._refresh_live)

    def apply_theme(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(css_for(read_colors()).encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _fill(self) -> None:
        apps = [info for info in Gio.AppInfo.get_all() if include_app(info)]
        apps.sort(key=lambda info: (0 if (info.get_name() or "").lower() == "steam" else 1, (info.get_name() or "").lower()))
        for info in apps:
            wm_class = class_from_desktop(info)
            app_id = info.get_id() or wm_class or (info.get_name() or "")
            override = (self.overrides.get(app_id) or {}).get("mode") or "default"
            if not wm_class and self.overrides.get(app_id):
                wm_class = self.overrides[app_id].get("class") or ""
            mode, source = describe_state(wm_class, override, self.configured, self.clients)
            row = AppRow(info, wm_class, mode, source, override)
            self.rows.append(row)
            self.listbox.append(row)
        if self.rows:
            self.listbox.select_row(self.rows[0])

    def _on_search(self, entry: Gtk.Entry) -> None:
        query = entry.get_text().strip().lower()
        first = None
        for row in self.rows:
            visible = row.matches(query)
            row.set_visible(visible)
            if visible and first is None:
                first = row
        if first:
            self.listbox.select_row(first)

    def _selected(self) -> AppRow | None:
        row = self.listbox.get_selected_row()
        return row if isinstance(row, AppRow) else None

    def set_mode(self, row: AppRow, mode: str) -> None:
        app_id = row.info.get_id() or row.wm_class or (row.info.get_name() or "")
        if mode == "default":
            self.overrides.pop(app_id, None)
        else:
            self.overrides[app_id] = {
                "class": row.wm_class,
                "name": row.info.get_name() or app_id,
                "mode": mode,
            }
        save_overrides(self.overrides)
        reload_hyprland()
        row.override = mode
        row.mode, row.source = describe_state(row.wm_class, mode, self.configured, live_clients())
        labels = row.get_child().get_first_child().get_next_sibling()
        status = labels.get_last_child()
        if isinstance(status, Gtk.Label):
            status.set_text(f"{MODE_LABELS.get(row.mode, row.mode)} · {row.source}")
        row._paint_radios()

    def _refresh_live(self) -> bool:
        self.clients = live_clients()
        for row in self.rows:
            if not row.get_visible():
                continue
            mode, source = describe_state(row.wm_class, row.override, self.configured, self.clients)
            if mode == row.mode and source == row.source:
                continue
            row.mode, row.source = mode, source
            labels = row.get_child().get_first_child().get_next_sibling()
            status = labels.get_last_child()
            if isinstance(status, Gtk.Label):
                status.set_text(f"{MODE_LABELS.get(mode, mode)} · {source}")
        return True

    def _on_key(self, _ctrl, keyval, _code, _state) -> bool:
        key = Gdk.keyval_name(keyval) or ""
        if key in ("q", "Q", "Escape"):
            self.close()
            return True
        if key == "slash":
            self.search.grab_focus()
            return True
        row = self._selected()
        if key in ("j", "Down") and row:
            nxt = row.get_next_sibling()
            while nxt and not nxt.get_visible():
                nxt = nxt.get_next_sibling()
            if isinstance(nxt, AppRow):
                self.listbox.select_row(nxt)
                nxt.grab_focus()
            return True
        if key in ("k", "Up") and row:
            prev = row.get_prev_sibling()
            while prev and not prev.get_visible():
                prev = prev.get_prev_sibling()
            if isinstance(prev, AppRow):
                self.listbox.select_row(prev)
                prev.grab_focus()
            return True
        keys = {"1": "default", "2": "tiled", "3": "float", "4": "center", "5": "fullscreen"}
        if key in keys and row:
            self.set_mode(row, keys[key])
            return True
        return False


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.omarchy.omawin")

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = Omawin(self)
        win.present()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if "--print" in argv:
        clients = live_clients()
        configured = configured_modes()
        overrides = load_overrides()
        for info in sorted(Gio.AppInfo.get_all(), key=lambda item: (item.get_name() or "").lower()):
            if not include_app(info):
                continue
            wm_class = class_from_desktop(info)
            app_id = info.get_id() or wm_class
            override = (overrides.get(app_id) or {}).get("mode")
            mode, source = describe_state(wm_class, override, configured, clients)
            print(f"{info.get_name()}\t{wm_class}\t{mode}\t{source}")
        return 0
    return Application().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
