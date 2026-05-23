"""
FTS Theme Plugin

Description:
This plugin lets you customize your FTS TUI theme from a readable config file

How it works:
- On first run, it creates a `theme.ini` file in the plugin directory with default Arctic colors.
- Loads the theme automatically when FTS starts, applying colors to the TUI.
- Supports light customization via the `theme.ini` file, including primary, secondary, accent, foreground, background, and panel colors.
- Variables like cursor style, input selection, and footer key color are also configurable.
      See "https://textual.textualize.io/guide/design/#__tabbed_1_2" for more information.

Why use it:
- Gives FTS a visually appealing and consistent dark theme.
- Provides an easy way to customize your FTS TUI theme and make FTS app your own.
- Easy to tweak via the generated `theme.ini` file without touching plugin code.

Usage:
- Place this plugin in your FTS plugin directory.
- Restart FTS — the Arctic theme is applied automatically.
- Optionally, edit `theme.ini` to adjust colors or variables.
"""

import configparser
import os

from textual.theme import Theme

import fts.app.main as main
from fts.app.config import PLUGIN_DIR
from fts.app.backend.plugins.utils import copy_func

THEME_PATH = os.path.join(PLUGIN_DIR, "theme.ini")

DEFAULT_THEME = Theme(
    name="arctic",
    primary="#88C0D0",
    secondary="#81A1C1",
    accent="#B48EAD",
    foreground="#D8DEE9",
    background="#2E3440",
    success="#A3BE8C",
    warning="#EBCB8B",
    error="#BF616A",
    surface="#222228",
    panel="#434C5E",
    dark=True,
    variables={
        "block-cursor-text-style": "none",
        "footer-key-foreground": "#88C0D0",
        "input-selection-background": "#81a1c1 35%",
    },
)


def save_default_theme():
    config = configparser.RawConfigParser()
    config["Theme"] = {
        "name": DEFAULT_THEME.name,
        "primary": DEFAULT_THEME.primary,
        "secondary": DEFAULT_THEME.secondary,
        "accent": DEFAULT_THEME.accent,
        "foreground": DEFAULT_THEME.foreground,
        "background": DEFAULT_THEME.background,
        "success": DEFAULT_THEME.success,
        "warning": DEFAULT_THEME.warning,
        "error": DEFAULT_THEME.error,
        "surface": DEFAULT_THEME.surface,
        "panel": DEFAULT_THEME.panel,
        "dark": str(DEFAULT_THEME.dark),
    }
    config["Variables"] = DEFAULT_THEME.variables

    with open(THEME_PATH, "w") as f:
        config.write(f)


def load_theme():
    if not os.path.exists(THEME_PATH):
        print(f"[Theme] No theme.ini found, creating default '{DEFAULT_THEME.name}' theme.")
        save_default_theme()

    config = configparser.RawConfigParser()
    config.read(THEME_PATH)

    theme_section = config["Theme"]
    vars_section = dict(config["Variables"]) if "Variables" in config else {}

    return Theme(
        name=theme_section.get("name", "error"),
        primary=theme_section.get("primary", "#FF13F0"),
        secondary=theme_section.get("secondary", "#FF13F0"),
        accent=theme_section.get("accent", "#FF13F0"),
        foreground=theme_section.get("foreground", "#FF13F0"),
        background=theme_section.get("background", "#FF13F0"),
        success=theme_section.get("success", "#FF13F0"),
        warning=theme_section.get("warning", "#FF13F0"),
        error=theme_section.get("error", "#FF13F0"),
        surface=theme_section.get("surface", "#FF13F0"),
        panel=theme_section.get("panel", "#FF13F0"),
        dark=theme_section.getboolean("dark", False),
        variables=vars_section,
    )

original_on_mount = None

def set_theme(self):
    global original_on_mount
    original_on_mount(self)
    new_theme = load_theme()
    self.register_theme(new_theme)
    self.theme = new_theme.name


def setup_plugin():
    global original_on_mount
    original_on_mount = copy_func(main.FTSApp.on_mount)
    main.FTSApp.on_mount = set_theme
