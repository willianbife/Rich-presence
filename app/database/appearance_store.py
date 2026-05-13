from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppearanceSettings:
    theme_name: str = "Aurora Glass"
    accent: str = "#64e8ff"
    blur: int = 26
    card_opacity: int = 78
    wallpaper_path: str = ""


class AppearanceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("data") / "appearance.json"
        self.wallpaper_dir = self.path.parent / "wallpapers"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppearanceSettings:
        if not self.path.exists():
            settings = AppearanceSettings()
            self.save(settings)
            return settings
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AppearanceSettings(
                theme_name=data.get("theme_name", "Aurora Glass"),
                accent=data.get("accent", "#64e8ff"),
                blur=int(data.get("blur", 26)),
                card_opacity=max(72, int(data.get("card_opacity", 78))),
                wallpaper_path=data.get("wallpaper_path", ""),
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return AppearanceSettings()

    def save(self, settings: AppearanceSettings) -> None:
        self.path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")

    def import_wallpaper(self, source: Path) -> str:
        suffix = source.suffix.lower() if source.suffix else ".png"
        target = self.wallpaper_dir / f"custom_wallpaper{suffix}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return str(target)
