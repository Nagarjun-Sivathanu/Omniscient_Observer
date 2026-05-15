"""
Skill extraction — derive a fine-grained skill label from (app_key, title).

A "skill" is more specific than the coarse activity category. Where category
says "productive", a skill says "Python" or "FastAPI" or "Git".

This is a pure, deterministic function of data we already store in
activity_snapshots (app_key + window title). No LLM, no GPU, no extra
persistence — the skill graph is computed at query time. Window title is
the strongest signal we have ("pipeline.py - ... - Visual Studio Code").

Returns None when nothing recognisable is found, so the skill graph stays
clean instead of filling with noise.
"""
import re

# ── Source-file extension → language skill ────────────────────────────────────
_EXT_SKILL: dict[str, str] = {
    "py": "Python", "ipynb": "Python",
    "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript",
    "rs": "Rust", "go": "Go", "java": "Java", "kt": "Kotlin",
    "rb": "Ruby", "php": "PHP", "swift": "Swift",
    "c": "C", "h": "C", "cpp": "C++", "cc": "C++", "hpp": "C++", "cxx": "C++",
    "cs": "C#", "scala": "Scala", "dart": "Dart", "lua": "Lua",
    "html": "HTML", "htm": "HTML", "css": "CSS", "scss": "CSS", "sass": "CSS",
    "sql": "SQL", "sh": "Shell", "bash": "Shell", "zsh": "Shell",
    "ps1": "PowerShell", "psm1": "PowerShell",
    "md": "Writing", "rst": "Writing", "txt": "Writing",
    "json": "Config", "yaml": "Config", "yml": "Config", "toml": "Config",
    "ini": "Config", "env": "Config", "xml": "Config",
}

_FILE_RE = re.compile(r"\b[\w.\-]+\.([a-z0-9]{1,6})\b", re.IGNORECASE)

# ── Tech keyword → skill (matched as whole words, lowercase) ───────────────────
_KEYWORD_SKILL: dict[str, str] = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "react": "React", "vue": "Vue", "angular": "Angular", "svelte": "Svelte",
    "nextjs": "Next.js", "next.js": "Next.js", "node": "Node.js", "nodejs": "Node.js",
    "tailwind": "Tailwind", "bootstrap": "CSS",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "terraform": "Terraform", "ansible": "Ansible",
    "tensorflow": "Machine Learning", "pytorch": "Machine Learning",
    "keras": "Machine Learning", "scikit": "Machine Learning",
    "huggingface": "Machine Learning", "transformers": "Machine Learning",
    "pandas": "Data Analysis", "numpy": "Data Analysis", "matplotlib": "Data Analysis",
    "jupyter": "Data Analysis",
    "git": "Git", "github": "Git", "gitlab": "Git",
    "linux": "Linux", "ubuntu": "Linux", "bash": "Shell",
    "aws": "AWS", "azure": "Azure", "gcp": "Google Cloud",
    "postgres": "SQL", "postgresql": "SQL", "mysql": "SQL", "sqlite": "SQL",
    "mongodb": "MongoDB", "redis": "Redis",
    "ollama": "LLM / AI", "langchain": "LLM / AI", "chromadb": "LLM / AI",
    "anthropic": "LLM / AI", "openai": "LLM / AI",
}

# Editors / IDEs — if a file/keyword match fails, attribute to generic "Coding"
_EDITOR_HINTS = (
    "visual studio code", "vscode", "pycharm", "intellij", "webstorm",
    "sublime text", "neovim", "vim ", "emacs", "android studio", "rider",
)

# Learning / reference domains seen in browser titles
_LEARNING_HINTS = (
    "stack overflow", "stackoverflow", "mdn", "w3schools", "geeksforgeeks",
    "arxiv", "coursera", "udemy", "khan academy", "freecodecamp",
    "developer.mozilla", "docs.python", "readthedocs", "dev.to", "medium",
)

_STRIP = (" - visual studio code", " — visual studio code")


def extract_skill(app_key: str, title: str = "") -> str | None:
    """Return a skill label for an (app_key, title) pair, or None if unknown."""
    app_key = (app_key or "").lower()
    raw = (title or "")
    low = (raw + " " + app_key).lower()

    # 1. Source file extension in the title → language
    for m in _FILE_RE.finditer(raw):
        ext = m.group(1).lower()
        if ext in _EXT_SKILL:
            return _EXT_SKILL[ext]

    # 2. Tech keyword (whole-word) anywhere in title or app
    for kw, skill in _KEYWORD_SKILL.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", low):
            return skill

    # 3. In an editor/IDE but no recognisable file/keyword → generic Coding
    if any(h in low for h in _EDITOR_HINTS):
        return "Coding"

    # 4. Browser on a known learning/reference site → Learning
    if any(h in low for h in _LEARNING_HINTS):
        return "Learning"

    # 5. Nothing recognisable — keep the graph clean
    return None
