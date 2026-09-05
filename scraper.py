"""
scraper.py — Baja datos de rock.com.ar para construir la red de colaboración
del rock argentino.

Uso:
    python scraper.py index                 # arma el índice completo de artistas
    python scraper.py artists                # visita cada ficha de artista
    python scraper.py discs                  # visita cada ficha de disco (créditos)
    python scraper.py all                    # corre todo en secuencia
    python scraper.py all --limit 200        # para pruebas rápidas (sólo N artistas)

Salidas (todas en ./data):
    artist_index.json   -> {slug: {"name":..., "url":...}}
    artists.json         -> {slug: {"name", "url", "bio_links": [slugs],
                                      "discography": [{"title","url","year"}]}}
    disc_credits.json    -> {disc_url: {"title":..., "raw_credit": "...",
                                          "resolved_slugs": [slugs]}}

Diseñado para ser interrumpible: usa caché en disco (cache/) y guarda progreso
incremental, así que se puede cortar con Ctrl+C y retomar después.
"""
import argparse
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from common import BASE, fetch, load_json, save_json, normalize_name, slugify

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LETTERS = list("abcdefghijklmnopqrstuvwxyz") + ["00"]

ARTIST_URL_RE = re.compile(r"^https?://rock\.com\.ar/artistas/([^/?#]+)/?$")
DISC_URL_RE = re.compile(r"^https?://rock\.com\.ar/discos/([^/?#]+)/?$")


def _abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE.rstrip("/") + "/" + href.lstrip("/")


# ---------------------------------------------------------------------------
# 1. Índice de artistas: /enciclopedia/ -> /abc/{letra}/ (con paginación)
# ---------------------------------------------------------------------------

def build_artist_index(max_pages_per_letter=200, override_robots_delay=None):
    index_path = DATA_DIR / "artist_index.json"
    index = load_json(index_path, {})

    for letter in LETTERS:
        page = 1
        seen_this_letter = set()
        while page <= max_pages_per_letter:
            url = f"{BASE}/abc/{letter}/" if page == 1 else f"{BASE}/abc/{letter}/page/{page}/"
            html = fetch(url, override_robots_delay=override_robots_delay)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            found_new = False
            for a in soup.find_all("a", href=True):
                m = ARTIST_URL_RE.match(_abs_url(a["href"]))
                if not m:
                    continue
                slug = m.group(1)
                name = a.get_text(strip=True)
                if not name:
                    continue
                if slug not in index:
                    found_new = True
                if slug not in seen_this_letter:
                    seen_this_letter.add(slug)
                    index[slug] = {"name": name, "url": f"{BASE}/artistas/{slug}/"}
            print(f"  [{letter}] pág {page}: {len(seen_this_letter)} artistas acumulados")
            if not found_new and page > 1:
                break
            # heurística de corte: si la página no trajo ningún link de artista, cortar
            if not any(ARTIST_URL_RE.match(_abs_url(a["href"])) for a in soup.find_all("a", href=True)):
                break
            page += 1
            save_json(index, index_path)

    save_json(index, index_path)
    print(f"\nTotal de artistas indexados: {len(index)}")
    return index


# ---------------------------------------------------------------------------
# 2. Fichas de artista: biografía (links a otros artistas) + discografía
# ---------------------------------------------------------------------------

def scrape_artist_page(slug: str, url: str, override_robots_delay=None):
    html = fetch(url, override_robots_delay=override_robots_delay)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # todos los links a /artistas/ en la página = señal de colaboración /
    # mención directa (biografía, integrantes, proyectos paralelos, etc.)
    bio_links = set()
    for a in soup.find_all("a", href=True):
        m = ARTIST_URL_RE.match(_abs_url(a["href"]))
        if m and m.group(1) != slug:
            bio_links.add(m.group(1))

    # discografía: bloque de links a /discos/
    discography = []
    seen_discs = set()
    for a in soup.find_all("a", href=True):
        m = DISC_URL_RE.match(_abs_url(a["href"]))
        if not m:
            continue
        disc_url = _abs_url(a["href"])
        if disc_url in seen_discs:
            continue
        seen_discs.add(disc_url)
        title = a.get_text(strip=True)
        discography.append({"title": title, "url": disc_url})

    return {
        "name": soup.find("h1").get_text(strip=True) if soup.find("h1") else slug,
        "url": url,
        "bio_links": sorted(bio_links),
        "discography": discography,
    }


def scrape_all_artists(limit=None, override_robots_delay=None):
    index = load_json(DATA_DIR / "artist_index.json")
    if not index:
        print("No hay índice de artistas. Corré primero: python scraper.py index")
        sys.exit(1)

    artists = load_json(DATA_DIR / "artists.json", {})
    slugs = list(index.keys())
    if limit:
        slugs = slugs[:limit]

    pending = [s for s in slugs if s not in artists]
    if pending:
        print(f"  {len(pending)} fichas de artista por descargar (el resto ya está en caché)")

    for i, slug in enumerate(slugs, 1):
        if slug in artists:
            continue
        info = index[slug]
        try:
            data = scrape_artist_page(slug, info["url"], override_robots_delay=override_robots_delay)
        except Exception as e:
            print(f"  ! error en {slug}: {e}")
            continue
        if data:
            artists[slug] = data
        if i % 20 == 0 or i == len(slugs):
            save_json(artists, DATA_DIR / "artists.json")
            print(f"  {i}/{len(slugs)} artistas procesados")

    save_json(artists, DATA_DIR / "artists.json")
    print(f"\nTotal de fichas de artista descargadas: {len(artists)}")
    return artists


# ---------------------------------------------------------------------------
# 3. Fichas de disco: línea de crédito -> nombres -> slugs resueltos
# ---------------------------------------------------------------------------

def _build_name_lookup(index: dict):
    """Mapa nombre_normalizado -> slug, para resolver créditos de texto libre."""
    lookup = {}
    for slug, info in index.items():
        lookup[normalize_name(info["name"])] = slug
        # también probamos con el slug "adivinado" desde el nombre
        lookup.setdefault(normalize_name(slug.replace("-", " ")), slug)
    return lookup


def resolve_credit_names(raw_credit: str, lookup: dict):
    from common import split_credit_names
    resolved = []
    for name in split_credit_names(raw_credit):
        key = normalize_name(name)
        if key in lookup:
            resolved.append(lookup[key])
    return resolved


# Etiquetas comunes en fichas de disco de este tipo de enciclopedia. Si el
# sitio usa otra palabra, agregala a esta lista.
YEAR_LABELS = [
    r"fecha de edici[oó]n", r"a[nñ]o de edici[oó]n", r"edici[oó]n",
    r"a[nñ]o", r"lanzamiento", r"publicado",
]


def extract_year(soup):
    """Busca el año de edición del disco. Primero intenta cerca de una
    etiqueta conocida (ej. 'Fecha de edición: 1986'); si no la encuentra,
    busca el primer año de 4 dígitos razonable (1950-2029) en el texto
    de la página. Devuelve None si no encuentra nada confiable."""
    text = soup.get_text(" ", strip=True)

    for label in YEAR_LABELS:
        m = re.search(label + r"[^\d]{0,15}(19[5-9]\d|20[0-2]\d)", text, re.IGNORECASE)
        if m:
            return int(m.group(1))

    # respaldo: primer año de 4 dígitos que aparezca en los primeros 1000
    # caracteres de la página (donde suele estar la ficha técnica)
    m = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", text[:1000])
    if m:
        return int(m.group(1))
    return None


def scrape_all_discs(limit=None, override_robots_delay=None):
    index = load_json(DATA_DIR / "artist_index.json")
    artists = load_json(DATA_DIR / "artists.json", {})
    if not artists:
        print("No hay fichas de artista. Corré primero: python scraper.py artists")
        sys.exit(1)

    lookup = _build_name_lookup(index)

    # recolectar todas las URLs de disco únicas mencionadas en las fichas
    disc_urls = set()
    for a in artists.values():
        for d in a.get("discography", []):
            disc_urls.add(d["url"])

    if limit:
        disc_urls = set(list(disc_urls)[:limit])

    disc_credits = load_json(DATA_DIR / "disc_credits.json", {})

    pending = [u for u in disc_urls if u not in disc_credits]
    if pending:
        print(f"  {len(pending)} fichas de disco por descargar (el resto ya está en caché)")

    for i, url in enumerate(sorted(disc_urls), 1):
        if url in disc_credits:
            continue
        try:
            html = fetch(url, override_robots_delay=override_robots_delay)
        except Exception as e:
            print(f"  ! error en {url}: {e}")
            continue
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
        # la línea de crédito suele ser el primer h3/h4 debajo del título,
        # con un link al artista principal
        credit_tag = None
        for tag in soup.find_all(["h2", "h3", "h4"]):
            if tag.find("a", href=ARTIST_URL_RE) or True:
                credit_tag = tag
                break
        raw_credit = credit_tag.get_text(strip=True) if credit_tag else ""
        resolved = resolve_credit_names(raw_credit, lookup)
        year = extract_year(soup)
        disc_credits[url] = {
            "title": title,
            "raw_credit": raw_credit,
            "resolved_slugs": resolved,
            "year": year,
        }
        if i % 50 == 0 or i == len(disc_urls):
            save_json(disc_credits, DATA_DIR / "disc_credits.json")
            print(f"  {i}/{len(disc_urls)} discos procesados")

    save_json(disc_credits, DATA_DIR / "disc_credits.json")
    print(f"\nTotal de fichas de disco descargadas: {len(disc_credits)}")
    return disc_credits


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scraper de rock.com.ar",
        epilog="Por default, respeta el Request-rate real del robots.txt del "
               "sitio (1 request cada 10-20 min según la hora en Argentina). "
               "Esto es intencional y hace que una corrida completa tome "
               "semanas o meses — ver USAGE.md. Si conseguiste permiso "
               "explícito del sitio para ir más rápido, usá "
               "--override-robots-delay junto con --i-have-permission.",
    )
    parser.add_argument("cmd", choices=["index", "artists", "discs", "all"])
    parser.add_argument("--limit", type=int, default=None,
                         help="límite de artistas/discos a procesar (para pruebas; "
                              "no evita el rate limiting, solo acorta la lista)")
    parser.add_argument("--override-robots-delay", type=float, default=None,
                         help="ADVERTENCIA: ignora el Request-rate del robots.txt y usa "
                              "este delay fijo en segundos en su lugar. Requiere también "
                              "--i-have-permission. Sólo usar si conseguiste autorización "
                              "explícita de rock.com.ar para un crawl más rápido.")
    parser.add_argument("--i-have-permission", action="store_true",
                         help="confirma que --override-robots-delay se usa con permiso "
                              "explícito del sitio, no por impaciencia")
    args = parser.parse_args()

    if args.override_robots_delay is not None and not args.i_have_permission:
        parser.error(
            "--override-robots-delay requiere también --i-have-permission. "
            "El robots.txt de rock.com.ar pide explícitamente 1 request cada "
            "10-20 minutos (ver USAGE.md) — no lo aceleres sin autorización "
            "real del sitio."
        )
    override_delay = args.override_robots_delay if args.i_have_permission else None

    if override_delay is None:
        print("Rate limiting: respetando el robots.txt real de rock.com.ar "
              "(1 request cada 10-20 min según la hora). Esto puede tardar "
              "mucho — ver USAGE.md para tiempos estimados y alternativas.\n")

    t0 = time.time()
    if args.cmd in ("index", "all"):
        print("== Construyendo índice de artistas ==")
        build_artist_index(override_robots_delay=override_delay)
    if args.cmd in ("artists", "all"):
        print("\n== Descargando fichas de artista ==")
        scrape_all_artists(limit=args.limit, override_robots_delay=override_delay)
    if args.cmd in ("discs", "all"):
        print("\n== Descargando créditos de discos ==")
        scrape_all_discs(limit=args.limit, override_robots_delay=override_delay)
    print(f"\nListo en {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
