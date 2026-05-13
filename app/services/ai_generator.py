from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

from app.core.models import PresenceButton, PresenceConfig
from app.utils.logger import logger


GEMINI_MODEL_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={api_key}"
)


class AIGeneratorService:
    def generate(self, prompt: str, mode: str = "generate", current: PresenceConfig | None = None) -> PresenceConfig:
        prompt = prompt.strip()
        if not prompt and current is None:
            return self._fallback("Presenca criativa para Discord", "cyberpunk")

        api_key = self._api_key()
        if not api_key:
            logger.log("GEMINI_API_KEY ausente. Usando gerador local.", "warning")
            return self._fallback(prompt or current.details, current.mood if current else "cyberpunk")

        try:
            raw = self._call_gemini(api_key, prompt, mode, current)
            data = self._extract_json(raw)
            return self._config_from_ai(data)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429}:
                logger.log("Gemini recusou ou limitou a chamada. Usando fallback local.", "warning")
            else:
                logger.log(f"Falha HTTP na Gemini ({exc.code}). Usando fallback local.", "warning")
        except Exception as exc:
            logger.log(f"IA retornou algo invalido ({exc}). Usando fallback local.", "warning")

        return self._fallback(prompt or (current.details if current else ""), current.mood if current else "cyberpunk")

    def _api_key(self) -> str:
        value = os.getenv("GEMINI_API_KEY", "").strip()
        if self._looks_real_key(value):
            return value
        for env_path in self._env_candidates():
            try:
                env_file = open(env_path, "r", encoding="utf-8")
            except OSError:
                continue
            with env_file:
                for line in env_file:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if self._looks_real_key(value):
                            return value
        return ""

    def _env_candidates(self) -> list[str]:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        return [
            os.path.join(base, ".env"),
            os.path.join(os.getcwd(), ".env"),
        ]

    def _looks_real_key(self, value: str) -> bool:
        if not value:
            return False
        lowered = value.lower()
        placeholders = {"sua_chave_aqui", "cole_sua_chave_aqui", "your_api_key_here"}
        return lowered not in placeholders and len(value) > 20

    def _call_gemini(self, api_key: str, prompt: str, mode: str, current: PresenceConfig | None) -> str:
        system = (
            "Voce gera Rich Presence para Discord. Responda somente JSON valido, sem markdown. "
            "Use exatamente as chaves: title, details, state, large_text, small_text, large_image, "
            "small_image, rotating_phrases, buttons, mood. buttons deve ter no maximo 2 itens com label e url. "
            "URLs devem ser http ou https. Textos devem ser curtos e bons para Discord RPC. "
            "Obedeca o pedido do usuario: se ele pedir para alterar descricao/details, altere details; "
            "se pedir estado/status, altere state; se pedir frases, preencha rotating_phrases. "
            "Se ele pedir para ativar/conectar/aparecer no perfil, ainda assim retorne a melhor presenca em JSON; "
            "o aplicativo cuidara da conexao RPC."
        )
        current_payload = current.to_dict() if current else {}
        user = {
            "mode": mode,
            "description": prompt,
            "current_presence": current_payload,
        }
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": system},
                        {"text": json.dumps(user, ensure_ascii=False)},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.75,
                "maxOutputTokens": 900,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            GEMINI_MODEL_URL.format(api_key=api_key),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    def _extract_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Resposta da IA nao e um objeto JSON.")
        return data

    def _config_from_ai(self, data: dict[str, Any]) -> PresenceConfig:
        buttons = []
        for item in data.get("buttons", []):
            if isinstance(item, dict):
                buttons.append(PresenceButton(str(item.get("label", ""))[:32], str(item.get("url", ""))))
        while len(buttons) < 2:
            buttons.append(PresenceButton())

        phrases = data.get("rotating_phrases", [])
        if not isinstance(phrases, list):
            phrases = []

        return PresenceConfig(
            details=str(data.get("details") or data.get("title") or "")[:128],
            state=str(data.get("state", ""))[:128],
            large_image=str(data.get("large_image", ""))[:64],
            large_text=str(data.get("large_text", ""))[:128],
            small_image=str(data.get("small_image", ""))[:64],
            small_text=str(data.get("small_text", ""))[:128],
            rotating_phrases=[str(item).strip()[:128] for item in phrases if str(item).strip()][:12],
            buttons=buttons[:2],
            mood=str(data.get("mood", "cyberpunk"))[:32],
        )

    def _fallback(self, prompt: str, mood: str) -> PresenceConfig:
        seed = (prompt or "Presence Studio").strip()
        mood = (mood or "cyberpunk").strip().lower()
        lowered = seed.lower()
        
        # Categorização dinâmica baseada em palavras-chave
        categories = {
            "dev": ["codando", "programando", "codigo", "python", "node", "api", "debug", "terminal", "github"],
            "study": ["estud", "aula", "prova", "faculdade", "escola", "leitura", "pesquisa"],
            "gaming": ["jogando", "game", "valorant", "lol", "ranked", "partida", "fps", "rpg"],
            "music": ["musica", "spotify", "playlist", "ouvindo", "som", "batida"],
            "professional": ["profissional", "trabalho", "cliente", "reuniao", "projeto", "office"],
        }
        
        detected_mood = mood
        for cat, words in categories.items():
            if any(word in lowered for word in words):
                detected_mood = cat
                break

        templates = {
            "dev": ("Codando no modo foco", "Python | APIs | Discord RPC"),
            "study": ("Estudando com foco", "Anotacoes | Pesquisa | Disciplina"),
            "gaming": ("Jogando no modo ranked", "Partida ativa | GG"),
            "music": ("Ouvindo musica", "Playlist ligada | Vibe boa"),
            "professional": ("Trabalhando em projeto", "Planejamento | Execucao | Entrega"),
            "cyberpunk": ("Cyber Terminal", "Discord RPC | IA | Noite"),
        }
        
        default_details, default_state = templates.get(detected_mood, templates["cyberpunk"])
        
        # Tenta extrair algo útil do prompt para os detalhes
        ignored_action_words = [
            "quero que", "deixando no perfil que", "deixar no perfil que", 
            "ative", "ativar", "conecte", "conectar", "aparecer", "perfil", 
            "rich presence", "presenca", "coloca", "muda para", "gera um"
        ]
        
        cleaned = seed
        for word in ignored_action_words:
            cleaned = re.sub(r"\b" + re.escape(word) + r"\b", "", cleaned, flags=re.IGNORECASE).strip(" ,.-")
            
        details = default_details
        if cleaned and len(cleaned) > 3:
            # Capitaliza a primeira letra e limita tamanho
            details = cleaned[0].upper() + cleaned[1:96]
        elif seed:
            details = seed[0].upper() + seed[1:96]

        return PresenceConfig(
            details=details,
            state=default_state,
            large_image="studio",
            large_text="Modo inteligente (Fallback)",
            small_image="studio_small",
            small_text="Online no Presence Studio",
            rotating_phrases=[
                "Debugando o impossivel",
                "Construindo presenca inteligente",
                "Codando sem travar o PC",
            ],
            buttons=[
                PresenceButton("GitHub", "https://github.com/willianbife/Rich-presence"),
                PresenceButton("Projeto", "https://github.com/willianbife/Rich-presence"),
            ],
            mood=detected_mood,
        )
