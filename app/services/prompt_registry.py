from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from app.config import settings


class PromptRegistry:
    def __init__(self, root: str | Path | None = None, profile: str | None = None) -> None:
        self._root = Path(root or settings.prompt_root)
        self.profile = profile or settings.prompt_profile

    @property
    def version(self) -> str:
        return str(self._manifest()["profiles"][self.profile]["version"])

    def digest(self, capability: str, role: str) -> str:
        return hashlib.sha256(self.load(capability, role).encode("utf-8")).hexdigest()[:12]

    @lru_cache(maxsize=16)
    def load(self, capability: str, role: str) -> str:
        path = self._root / self.profile / capability / f"{role}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt nao encontrado: {path}")
        prompt = path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise ValueError(f"Prompt vazio: {path}")
        return prompt

    @lru_cache(maxsize=1)
    def _manifest(self) -> dict:
        path = self._root / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Manifesto de prompts nao encontrado: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        profiles = manifest.get("profiles", {})
        if self.profile not in profiles:
            raise ValueError(f"Perfil de prompts desconhecido: {self.profile}")
        return manifest


prompt_registry = PromptRegistry()
