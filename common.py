"""
Utilidades compartidas para el proyecto de red de colaboración de rock.com.ar
"""
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
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

# ---------------------------------------------------------------------------
# Rate limiting según robots.txt de rock.com.ar (revisado el 2026-09-05):
#
#   Crawl-delay: 60
#   Request-rate: 6/60m          (00:00–09:00 America/Argentina/Buenos_Aires)
#   Request-rate: 3/60m          (resto del día)
#
# Es decir: como mucho 1 request cada 10 minutos en el horario nocturno, y
# 1 cada 20 minutos el resto del día. Estos números son ÓRDENES DE MAGNITUD
# más lentos que un delay fijo de menos de un segundo — por eso el rate
# limiting se calcula automáticamente acá, en vez de dejarlo como un
# parámetro que alguien pueda bajar sin darse cuenta de la política real
# del sitio. Ver USAGE.md para el detalle y las implicancias de tiempo.
# ---------------------------------------------------------------------------
ROBOTS_TZ = "America/Argentina/Buenos_Aires"
ROBOTS_NIGHT_START_HOUR = 0   # 00:00 ART
ROBOTS_NIGHT_END_HOUR = 9     # 09:00 ART
ROBOTS_NIGHT_INTERVAL_SECONDS = 600     # 6 req / 60 min
ROBOTS_DAY_INTERVAL_SECONDS = 1200      # 3 req / 60 min

_last_request_monotonic = [None]  # estado del proceso, en una lista mutable


def _art_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(ROBOTS_TZ))
    except Exception:
        # Fallback si el sistema no tiene la base de datos de zonas horarias
        # instalada (poco común, pero posible). ART no tiene horario de
        # verano actualmente, así que un offset fijo de -3 es seguro.
        return datetime.now(timezone(timedelta(hours=-3)))


def _required_interval_seconds() -> int:
    hour = _art_now().hour
    if ROBOTS_NIGHT_START_HOUR <= hour < ROBOTS_NIGHT_END_HOUR:
        return ROBOTS_NIGHT_INTERVAL_SECONDS
    return ROBOTS_DAY_INTERVAL_SECONDS


def _throttle_for_robots(quiet: bool = False):
    """Bloquea lo necesario para respetar el Request-rate del robots.txt
    real del sitio, según la hora actual en Argentina."""
    required = _required_interval_seconds()
    now = time.monotonic()
    if _last_request_monotonic[0] is not None:
        elapsed = now - _last_request_monotonic[0]
        wait = required - elapsed
        if wait > 0:
            if not quiet:
                mins = wait / 60
                print(f"  (respetando robots.txt de rock.com.ar: esperando "
                      f"{wait:.0f}s / ~{mins:.1f} min antes del próximo request)")
            time.sleep(wait)
    _last_request_monotonic[0] = time.monotonic()


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


def fetch(url: str, retries: int = 3, force: bool = False,
          override_robots_delay: float = None) -> str:
    """Descarga una URL con caché en disco. Si la página ya está cacheada,
    la devuelve directo sin generar ningún request nuevo (ni esperar nada).

    Si hace falta un request real, respeta por default el Request-rate real
    del robots.txt de rock.com.ar (ver constantes arriba) — esto puede
    implicar esperas de 10-20 minutos entre páginas. Es intencional: no lo
    aceleres salvo que hayas conseguido permiso explícito del sitio (en cuyo
    caso podés pasar `override_robots_delay` con el valor acordado).
    """
    cpath = _cache_path(url)
    if cpath.exists() and not force:
        return cpath.read_text(encoding="utf-8", errors="ignore")

    last_err = None
    for attempt in range(retries):
        try:
            if override_robots_delay is not None:
                time.sleep(override_robots_delay)
            else:
                _throttle_for_robots()
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 404:
                cpath.write_text("", encoding="utf-8")
                return ""
            resp.raise_for_status()
            html = resp.text
            cpath.write_text(html, encoding="utf-8")
            return html
        except requests.RequestException as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last_err}")


def save_json(obj, path: str):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: str, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))
