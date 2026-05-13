from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_alt: str
    success: str
    warning: str
    danger: str


THEMES: dict[str, Theme] = {
    "Aurora Glass": Theme(
        name="Aurora Glass",
        background="#050711",
        surface="rgba(13, 18, 34, 0.62)",
        surface_alt="rgba(22, 30, 52, 0.74)",
        border="rgba(142, 247, 255, 0.20)",
        text="#f8fbff",
        muted="#a9b8d8",
        accent="#64e8ff",
        accent_alt="#9b6cff",
        success="#4dff9f",
        warning="#ffd166",
        danger="#ff5f7e",
    ),
    "Dark": Theme(
        name="Dark",
        background="#0f1117",
        surface="#171a23",
        surface_alt="#202432",
        border="#2d3345",
        text="#f5f7fb",
        muted="#9aa4b2",
        accent="#5dd4ff",
        accent_alt="#7c5cff",
        success="#47d18c",
        warning="#ffbf47",
        danger="#ff6978",
    ),
    "Cyberpunk": Theme(
        name="Cyberpunk",
        background="#090813",
        surface="#151226",
        surface_alt="#211833",
        border="#493261",
        text="#fff8ff",
        muted="#c5a9d8",
        accent="#00f5d4",
        accent_alt="#ff2bd6",
        success="#66ff99",
        warning="#ffe45e",
        danger="#ff3864",
    ),
    "Discord Roxo": Theme(
        name="Discord Roxo",
        background="#10121c",
        surface="#181b2b",
        surface_alt="#22263a",
        border="#303553",
        text="#ffffff",
        muted="#b8bdd3",
        accent="#5865f2",
        accent_alt="#9b6cff",
        success="#3ba55d",
        warning="#faa61a",
        danger="#ed4245",
    ),
    "Minimalista": Theme(
        name="Minimalista",
        background="#111315",
        surface="#1a1d20",
        surface_alt="#24282c",
        border="#343a40",
        text="#f4f1ea",
        muted="#aaa39a",
        accent="#89b4a7",
        accent_alt="#d7a86e",
        success="#7fc98f",
        warning="#d9b65d",
        danger="#d67b7b",
    ),
}
