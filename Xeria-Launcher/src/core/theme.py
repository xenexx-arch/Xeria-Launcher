import platform

IS_WIN = platform.system() == "Windows"
UI_FONT = "Segoe UI" if IS_WIN else "DejaVu Sans"
MONO_FONT = "Consolas" if IS_WIN else "DejaVu Sans Mono"

DARK_PALETTE = {
    "BG": "#1a1a1a", "BG2": "#232323", "BG3": "#2e2e2e",
    "BORDER": "#3d3d3d", "FG": "#e6e6e6", "GRAY": "#8a8a8a",
    "ACCENT": "#4a90e2", "ACCENT2": "#3a7bc8",
    "GREEN": "#5eb87d", "RED": "#e05c5c", "YELLOW": "#e0b85c",
    "CYAN": "#5cb8d8", "PURPLE": "#8a8a8a", "PINK": "#d88aa8",
    "ORANGE": "#e0895c", "BLUE": "#5c8ae0",
    "TEXT_ON_ACCENT": "#ffffff",
    "WHITE": "#ffffff",
    "BLACK": "#000000",
}

LIGHT_PALETTE = {
    "BG": "#f5f5f5", "BG2": "#e8e8e8", "BG3": "#dcdcdc",
    "BORDER": "#c4c4c4", "FG": "#202020", "GRAY": "#6a6a6a",
    "ACCENT": "#4a90e2", "ACCENT2": "#3a7bc8",
    "GREEN": "#3f9a5a", "RED": "#c94a5a", "YELLOW": "#b88a2a",
    "CYAN": "#3d8ca8", "PURPLE": "#6a6a6a", "PINK": "#c476a8",
    "ORANGE": "#c47a3f", "BLUE": "#5a7bd6",
    "TEXT_ON_ACCENT": "#ffffff",
    "WHITE": "#ffffff",
    "BLACK": "#000000",
}

ACCENTS = {
    "White":  {"ACCENT": "#ffffff", "ACCENT2": "#d0d0d0"},
    "Blue":   {"ACCENT": "#4a90e2", "ACCENT2": "#3a7bc8"},
    "Purple": {"ACCENT": "#9a6ce0", "ACCENT2": "#7a52c0"},
    "Green":  {"ACCENT": "#5eb87d", "ACCENT2": "#4a9668"},
    "Orange": {"ACCENT": "#e0895c", "ACCENT2": "#c07048"},
    "Red":    {"ACCENT": "#e05c5c", "ACCENT2": "#c04848"},
    "Pink":   {"ACCENT": "#d88aa8", "ACCENT2": "#b86e8c"},
    "Cyan":   {"ACCENT": "#5cb8d8", "ACCENT2": "#4a9ab8"},
}

BG      = DARK_PALETTE["BG"]
BG2     = DARK_PALETTE["BG2"]
BG3     = DARK_PALETTE["BG3"]
BORDER  = DARK_PALETTE["BORDER"]
FG      = DARK_PALETTE["FG"]
GRAY    = DARK_PALETTE["GRAY"]
ACCENT  = DARK_PALETTE["ACCENT"]
ACCENT2 = DARK_PALETTE["ACCENT2"]
GREEN   = DARK_PALETTE["GREEN"]
RED     = DARK_PALETTE["RED"]
YELLOW  = DARK_PALETTE["YELLOW"]
CYAN    = DARK_PALETTE["CYAN"]
PURPLE  = DARK_PALETTE["PURPLE"]
PINK    = DARK_PALETTE["PINK"]
ORANGE  = DARK_PALETTE["ORANGE"]
BLUE    = DARK_PALETTE["BLUE"]
DARK    = DARK_PALETTE["TEXT_ON_ACCENT"]
WHITE   = "#ffffff"
BLACK   = "#000000"

current_name = "dark"


def apply(name):
    global current_name
    current_name = "light" if name == "light" else "dark"
    palette = LIGHT_PALETTE if current_name == "light" else DARK_PALETTE
    g = globals()
    for k in ("BG", "BG2", "BG3", "BORDER", "FG", "GRAY",
              "ACCENT", "ACCENT2", "GREEN", "RED", "YELLOW",
              "CYAN", "PURPLE", "PINK", "ORANGE", "BLUE",
              "WHITE", "BLACK"):
        g[k] = palette[k]
    g["DARK"] = palette["TEXT_ON_ACCENT"]


def apply_accent(name):
    g = globals()
    a = ACCENTS.get(name, ACCENTS["White"])
    g["ACCENT"] = a["ACCENT"]
    g["ACCENT2"] = a["ACCENT2"]


def on_accent():
    a = (ACCENT or "#ffffff").lstrip("#")
    try:
        r, g, b = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    except Exception:
        return WHITE
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if lum > 0.6 else "#ffffff"
