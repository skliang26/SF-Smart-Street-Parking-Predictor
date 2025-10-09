# src/nl_llm.py
import os, re, json, requests
from typing import Dict, Any
from .nl_intent import parse_nl_query as fallback_rule_parser

# Simple JSON schema you want back
SCHEMA = {
    "origin_text": None,
    "walking_preference": None,   # "close" | "balanced" | "far"
    "radius_mi": None,            # float or null
    "units": None,                # "ft" | "mi"
    "duration_minutes": None,     # int or null
    "time": None,                 # string or null
    "top_n": None,                # int or null
}

PROMPT = """You are an information extractor.
Return ONLY one JSON object with these keys:
origin_text (string), walking_preference ("close"|"balanced"|"far"),
radius_mi (number or null), units ("ft"|"mi" or null),
duration_minutes (integer or null), time (string or null), top_n (integer or null).

Interpret this user request:
\"\"\"{query}\"\"\"

Rules:
- If unsure about a field, set it to null.
- Do not write anything except a single JSON object.
"""

def _extract_json(s: str) -> Dict[str, Any]:
    # Find the first JSON object in the text safely
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        # keep only expected keys
        out = {k: data.get(k, None) for k in SCHEMA.keys()}
        return out
    except Exception:
        return {}

def parse_nl_with_llm(text: str) -> Dict[str, Any]:
    """
    Try local Ollama first (free). If not available, fall back to the rule-based parser.
    """
    query = (text or "").strip()
    if not query:
        return {}

    # Prefer env var for model; good defaults: mistral, llama3, qwen2
    model = os.getenv("OLLAMA_MODEL", "mistral")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

    payload = {
        "model": model,
        "prompt": PROMPT.format(query=query),
        "stream": False,
    }

    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        # Ollama returns { "response": "...", ... }
        response_text = r.json().get("response", "")
        data = _extract_json(response_text)
        if data:
            return data
    except Exception:
        pass

    # Fallback to your offline heuristic parser
    return fallback_rule_parser(query)
