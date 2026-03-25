import os
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Persona:
    name: str
    description: str
    system_prompt: str


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_md(path: str) -> Optional[Persona]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None

    match = _FRONTMATTER_RE.match(raw)
    if not match:
        # No frontmatter: use filename as name, whole content as prompt
        stem = os.path.splitext(os.path.basename(path))[0]
        return Persona(name=stem, description="", system_prompt=raw.strip())

    front = match.group(1)
    body = raw[match.end():].strip()

    name = ""
    description = ""
    for line in front.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if k == "name":
                name = v
            elif k == "description":
                description = v

    stem = os.path.splitext(os.path.basename(path))[0]
    return Persona(name=name or stem, description=description, system_prompt=body)


class PersonaManager:
    def __init__(self, personas_dir: str, default_name: str = "default"):
        self.personas_dir = os.path.expanduser(personas_dir)
        self.default_name = default_name
        self._personas: dict[str, Persona] = {}

    def load_all(self) -> dict[str, Persona]:
        self._personas.clear()
        if not os.path.isdir(self.personas_dir):
            return self._personas

        for fname in os.listdir(self.personas_dir):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.personas_dir, fname)
            persona = _parse_md(path)
            if persona:
                # key by stem (filename without extension) for lookup
                stem = os.path.splitext(fname)[0]
                self._personas[stem] = persona

        return self._personas

    def get(self, name: str) -> Optional[Persona]:
        return self._personas.get(name)

    def get_default(self) -> Optional[Persona]:
        return self._personas.get(self.default_name)

    def list_all(self) -> list[Persona]:
        return list(self._personas.values())

    def get_system_prompt(self, name: str) -> str:
        persona = self.get(name)
        if persona:
            return persona.system_prompt
        default = self.get_default()
        if default:
            return default.system_prompt
        return "You are a helpful and friendly assistant."
