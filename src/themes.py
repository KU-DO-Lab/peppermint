from rich.color import Color
from textual.theme import BUILTIN_THEMES
from textual.theme import Theme as TextualTheme

BUILTIN_THEMES: dict[str, TextualTheme] = {
    "oxocarbon": TextualTheme(
        # https://github.com/nyoom-engineering/oxocarbon/blob/main/docs/style-guide.md
        name="oxocarbon",
        primary="#33b1ff", 
        secondary="#be95ff", 
        warning="#3bbdb9", 
        error="#ee5396", 
        success="#42be65", 
        accent="#82cfff", 
        surface="#262626", 
        panel="#393939", 
        background="#161616", 
        dark=True,
        variables={
            "input-selection-background": "#08bdba 35%",
        },
    ),
    "sunset": TextualTheme(
        name="sunset",
        primary="#FF7E5F",
        secondary="#FEB47B",
        warning="#FFD93D",
        error="#FF5757",
        success="#98D8AA",
        accent="#B983FF",
        background="#2B2139",
        surface="#362C47",
        panel="#413555",
        dark=True,
        variables={
            "input-cursor-background": "#FF7E5F",
            "input-selection-background": "#FF7E5F 35%",
            "footer-background": "transparent",
            "button-color-foreground": "#2B2139",
            "method-get": "#FF7E5F",
        },
    ),
    "aurora": TextualTheme(
        name="aurora",
        primary="#45FFB3",
        secondary="#A1FCDF",
        accent="#DF7BFF",
        warning="#FFE156",
        error="#FF6B6B",
        success="#64FFDA",
        background="#0A1A2F",
        surface="#142942",
        panel="#1E3655",
        dark=True,
        variables={
            "input-cursor-background": "#45FFB3",
            "input-selection-background": "#45FFB3 35%",
            "footer-background": "transparent",
            "button-color-foreground": "#0A1A2F",
            "method-post": "#DF7BFF",
        },
    ),
    "nautilus": TextualTheme(
        name="nautilus",
        primary="#0077BE",
        secondary="#20B2AA",
        warning="#FFD700",
        error="#FF6347",
        success="#32CD32",
        accent="#FF8C00",
        background="#001F3F",
        surface="#003366",
        panel="#005A8C",
        dark=True,
    ),
    "cobalt": TextualTheme(
        name="cobalt",
        primary="#334D5C",
        secondary="#66B2FF",
        warning="#FFAA22",
        error="#E63946",
        success="#4CAF50",
        accent="#D94E64",
        surface="#27343B",
        panel="#2D3E46",
        background="#1F262A",
        dark=True,
        variables={
            "input-selection-background": "#4A9CFF 35%",
        },
    ),
    "twilight": TextualTheme(
        name="twilight",
        primary="#367588",
        secondary="#5F9EA0",
        warning="#FFD700",
        error="#FF6347",
        success="#00FA9A",
        accent="#FF7F50",
        background="#191970",
        surface="#3B3B6D",
        panel="#4C516D",
        dark=True,
    ),
    "hacker": TextualTheme(
        name="hacker",
        primary="#00FF00",
        secondary="#3A9F3A",
        warning="#00FF66",
        error="#FF0000",
        success="#00DD00",
        accent="#00FF33",
        background="#000000",
        surface="#0A0A0A",
        panel="#111111",
        dark=True,
        variables={
            "method-get": "#00FF00",
            "method-post": "#00DD00",
            "method-put": "#00BB00",
            "method-delete": "#FF0000",
            "method-patch": "#00FF33",
            "method-options": "#3A9F3A",
            "method-head": "#00FF66",
        },
    ),
    "manuscript": TextualTheme(
        name="manuscript",
        primary="#2C4251",  # Ink blue
        secondary="#6B4423",  # Aged leather brown
        accent="#8B4513",  # Rich leather accent
        warning="#B4846C",  # Faded sepia
        error="#A94442",  # Muted red ink
        success="#2D5A27",  # Library green
        background="#F5F1E9",  # Aged paper
        surface="#EBE6D9",  # Textured paper
        panel="#E0DAC8",  # Parchment
        dark=False,
        variables={
            "input-cursor-background": "#2C4251",
            "input-selection-background": "#2C4251 25%",
            "footer-background": "#2C4251",
            "footer-key-foreground": "#F5F1E9",
            "footer-description-foreground": "#F5F1E9",
            "button-color-foreground": "#F5F1E9",
            "method-get": "#2C4251",  # Ink blue
            "method-post": "#2D5A27",  # Library green
            "method-put": "#6B4423",  # Leather brown
            "method-delete": "#A94442",  # Red ink
            "method-patch": "#8B4513",  # Rich leather
            "method-options": "#4A4A4A",  # Dark gray ink
            "method-head": "#5C5C5C",  # Gray ink
        },
    ),
}
