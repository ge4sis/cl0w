import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Skill:
    name: str
    description: str
    usage: str
    template: str


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_md(path: str) -> Optional[Skill]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None

    match = _FRONTMATTER_RE.match(raw)
    if not match:
        stem = os.path.splitext(os.path.basename(path))[0]
        return Skill(name=stem, description="", usage=f"/{stem} <input>", template=raw.strip())

    front = match.group(1)
    body = raw[match.end():].strip()

    name = description = usage = ""
    for line in front.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if k == "name":
                name = v
            elif k == "description":
                description = v
            elif k == "usage":
                usage = v

    stem = os.path.splitext(os.path.basename(path))[0]
    name = name or stem
    usage = usage or f"/{name} <input>"
    return Skill(name=name, description=description, usage=usage, template=body)


class SkillManager:
    def __init__(self, skills_dir: str):
        self.skills_dir = os.path.expanduser(skills_dir)
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        self._skills.clear()
        if not os.path.isdir(self.skills_dir):
            return self._skills

        for fname in os.listdir(self.skills_dir):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.skills_dir, fname)
            skill = _parse_md(path)
            if skill:
                stem = os.path.splitext(fname)[0]
                self._skills[stem] = skill

        return self._skills

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def render(self, name: str, args: list[str], context: str = "") -> Optional[str]:
        """
        Render a skill template.
        - {{input}}: args joined as string, or context if no args
        - {{language}}: first arg (for skills like translate)
        - {{arg1}}, {{arg2}}, ...: positional args
        """
        skill = self.get(name)
        if not skill:
            return None

        text = skill.template

        if args:
            input_text = " ".join(args)
        else:
            input_text = context

        text = text.replace("{{input}}", input_text)
        text = text.replace("{{context}}", context)

        if args:
            text = text.replace("{{language}}", args[0])
            for i, arg in enumerate(args, 1):
                text = text.replace(f"{{{{arg{i}}}}}", arg)

        return text
