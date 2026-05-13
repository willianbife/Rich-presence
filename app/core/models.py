from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


@dataclass
class PresenceButton:
    label: str = ""
    url: str = ""

    def is_valid(self) -> bool:
        url = self.url.strip()
        if not url:
            return False
        
        # Tenta corrigir URLs sem esquema
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            
        try:
            parsed = urlparse(url)
            return bool(self.label.strip() and parsed.scheme in {"http", "https"} and parsed.netloc and "." in parsed.netloc)
        except Exception:
            return False


@dataclass
class PresenceConfig:
    details: str = "Criando algo incrível"
    state: str = "Discord Rich Presence Studio"
    large_image: str = ""
    large_text: str = ""
    small_image: str = ""
    small_text: str = ""
    rotating_phrases: list[str] = field(default_factory=list)
    mood: str = "cyberpunk"
    buttons: list[PresenceButton] = field(default_factory=lambda: [PresenceButton(), PresenceButton()])
    timestamp_enabled: bool = True
    start_timestamp: int | None = None

    def ensure_timestamp(self) -> None:
        if self.timestamp_enabled:
            if self.start_timestamp is None:
                self.start_timestamp = int(time())
        else:
            self.start_timestamp = None

    def to_rpc_payload(self) -> dict[str, Any]:
        self.ensure_timestamp()
        payload: dict[str, Any] = {
            "details": self.details.strip() or None,
            "state": self.state.strip() or None,
            "large_image": self.large_image.strip() or None,
            "large_text": self.large_text.strip() or None,
            "small_image": self.small_image.strip() or None,
            "small_text": self.small_text.strip() or None,
            "start": self.start_timestamp if self.timestamp_enabled else None,
        }

        valid_buttons = [asdict(button) for button in self.buttons if button.is_valid()]
        if valid_buttons:
            payload["buttons"] = valid_buttons[:2]

        return {key: value for key, value in payload.items() if value not in ("", None, [])}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PresenceConfig":
        buttons = data.get("buttons", [])
        parsed_buttons = [
            PresenceButton(label=item.get("label", ""), url=item.get("url", ""))
            for item in buttons
            if isinstance(item, dict)
        ]
        while len(parsed_buttons) < 2:
            parsed_buttons.append(PresenceButton())

        return cls(
            details=data.get("details", ""),
            state=data.get("state", ""),
            large_image=data.get("large_image", ""),
            large_text=data.get("large_text", ""),
            small_image=data.get("small_image", ""),
            small_text=data.get("small_text", ""),
            rotating_phrases=[str(item) for item in data.get("rotating_phrases", []) if str(item).strip()],
            mood=data.get("mood", "cyberpunk"),
            buttons=parsed_buttons[:2],
            timestamp_enabled=bool(data.get("timestamp_enabled", True)),
            start_timestamp=data.get("start_timestamp"),
        )


@dataclass
class Preset:
    name: str
    config: PresenceConfig
    id: str = field(default_factory=lambda: str(uuid4()))
    favorite: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "favorite": self.favorite,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preset":
        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", "Preset sem nome"),
            config=PresenceConfig.from_dict(data.get("config", {})),
            favorite=bool(data.get("favorite", False)),
        )
