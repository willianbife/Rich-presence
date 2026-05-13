from __future__ import annotations

import json
from pathlib import Path

from app.core.models import PresenceConfig, Preset


class PresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("data") / "presets.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Preset]:
        if not self.path.exists():
            return self._create_defaults()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            presets = [Preset.from_dict(item) for item in data.get("presets", [])]
            return self._merge_defaults(presets)
        except (json.JSONDecodeError, OSError, TypeError):
            return self._create_defaults()

    def save(self, presets: list[Preset]) -> None:
        payload = {"presets": [preset.to_dict() for preset in presets]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_from(self, file_path: Path) -> list[Preset]:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        raw_presets = data.get("presets", data if isinstance(data, list) else [])
        return [Preset.from_dict(item) for item in raw_presets]

    def export_to(self, file_path: Path, presets: list[Preset]) -> None:
        payload = {"presets": [preset.to_dict() for preset in presets]}
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _create_defaults(self) -> list[Preset]:
        presets = self._default_presets()
        self.save(presets)
        return presets

    def _merge_defaults(self, presets: list[Preset]) -> list[Preset]:
        existing = {preset.name.lower() for preset in presets}
        changed = False
        for preset in self._default_presets():
            if preset.name.lower() not in existing:
                presets.append(preset)
                changed = True
        if changed:
            self.save(presets)
        return presets

    def _default_presets(self) -> list[Preset]:
        return [
            Preset(
                name="Programando",
                config=PresenceConfig(
                    details="Codando no modo foco",
                    state="Python | APIs | Discord RPC",
                    large_image="code",
                    large_text="Modo dev ativado",
                    rotating_phrases=["Debugando com calma", "Construindo algo limpo", "Deploy mental em progresso"],
                    mood="dev",
                ),
            ),
            Preset(
                name="Estudando",
                config=PresenceConfig(
                    details="Estudando e anotando ideias",
                    state="Foco total",
                    large_image="study",
                    large_text="Aprendizado em andamento",
                    rotating_phrases=["Revisando conceitos", "Foco sem ruido", "Mais uma pagina vencida"],
                    mood="study",
                ),
            ),
            Preset("Jogando", PresenceConfig("Partida em andamento", "Modo gamer", "game", "GG sem rage", mood="gaming")),
            Preset("Ouvindo musica", PresenceConfig("Playlist ligada", "Vibes no Discord", "music", "Som ambiente", mood="music")),
            Preset("Cyberpunk", PresenceConfig("Cyber Terminal", "Neon | APIs | noite", "cyber", "Modo neon", mood="cyberpunk")),
            Preset("Dark", PresenceConfig("Trabalhando em silencio", "Dark mode permanente", "dark", "Minimal dark", mood="dark")),
            Preset("Profissional", PresenceConfig("Disponivel para projetos", "Buildando solucoes", "work", "Presence Studio", mood="professional")),
            Preset("Shitpost", PresenceConfig("Compilando cafe em bug", "100% oficial talvez", "meme", "Modo caos controlado", mood="shitpost")),
        ]
