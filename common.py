"""
Utilidades compartidas para el proyecto de red de colaboración de rock.com.ar
"""
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

BASE = "https://rock.com.ar"
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RockArNetworkResearch/1.0; "
        "uso personal/no comercial, contacto: reemplazar@tuemail.com)"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def slugify(name: str) -> str:
    """Aproxima el slug que usaría WordPress para un nombre de artista."""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def normalize_name(name: str) -> str:
    """Normaliza un nombre para poder comparar/matchear con tolerancia
    a acentos, mayúsculas, & vs 'y', artículos, etc."""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.replace("&", " y ")
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def split_credit_names(credit_text: str):
    """Divide una línea de crédito tipo 'Charly Garcia y Pedro Aznar' o
    'Charly Garcia, Pedro Aznar y Enrique Pinti' en nombres individuales."""
    if not credit_text:
        return []
    text = credit_text.replace("&", ",")
    # separar por " y " sólo cuando NO es parte de un nombre propio con "y"
    # (heurística simple: se usa como conector antes de la última parte)
    text = re.sub(r"\s+y\s+", ",", text)
    parts = [p.strip() for p in text.split(",")]
    return [p for p in parts if p]


def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()
    return CACHE_DIR / f"{h}.html"


def fetch(url: str, delay: float = 0.8, retries: int = 3, force: bool = False) -> str:
    """Descarga una URL con caché en disco y rate limiting básico.
    Guarda el HTML crudo en cache/ para poder re-correr el análisis
    sin volver a pegarle al sitio."""
    cpath = _cache_path(url)
    if cpath.exists() and not force:
        return cpath.read_text(encoding="utf-8", errors="ignore")

    last_err = None
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 404:
                cpath.write_text("", encoding="utf-8")
                return ""
            resp.raise_for_status()
            html = resp.text
            cpath.write_text(html, encoding="utf-8")
            time.sleep(delay)
            return html
        except requests.RequestException as e:
            last_err = e
            time.sleep(delay * (attempt + 1) * 2)
    raise RuntimeError(f"No se pudo descargar {url}: {last_err}")


def save_json(obj, path: str):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: str, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))
