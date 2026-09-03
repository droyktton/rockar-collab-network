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

def build_artist_index(delay=0.8, max_pages_per_letter=200):
    index_path = DATA_DIR / "artist_index.json"
    index = load_json(index_path, {})

    for letter in LETTERS:
        page = 1
        seen_this_letter = set()
        while page <= max_pages_per_letter:
            url = f"{BASE}/abc/{letter}/" if page == 1 else f"{BASE}/abc/{letter}/page/{page}/"
            html = fetch(url, delay=delay)
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

def scrape_artist_page(slug: str, url: str, delay=0.8):
    html = fetch(url, delay=delay)
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


def scrape_all_artists(delay=0.8, limit=None):
    index = load_json(DATA_DIR / "artist_index.json")
    if not index:
        print("No hay índice de artistas. Corré primero: python scraper.py index")
        sys.exit(1)

    artists = load_json(DATA_DIR / "artists.json", {})
    slugs = list(index.keys())
    if limit:
        slugs = slugs[:limit]

    for i, slug in enumerate(slugs, 1):
        if slug in artists:
            continue
        info = index[slug]
        try:
            data = scrape_artist_page(slug, info["url"], delay=delay)
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


def scrape_all_discs(delay=0.8, limit=None):
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

    for i, url in enumerate(sorted(disc_urls), 1):
        if url in disc_credits:
            continue
        try:
            html = fetch(url, delay=delay)
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
        disc_credits[url] = {
            "title": title,
            "raw_credit": raw_credit,
            "resolved_slugs": resolved,
        }
        if i % 50 == 0 or i == len(disc_urls):
            save_json(disc_credits, DATA_DIR / "disc_credits.json")
            print(f"  {i}/{len(disc_urls)} discos procesados")

    save_json(disc_credits, DATA_DIR / "disc_credits.json")
    print(f"\nTotal de fichas de disco descargadas: {len(disc_credits)}")
    return disc_credits


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper de rock.com.ar")
    parser.add_argument("cmd", choices=["index", "artists", "discs", "all"])
    parser.add_argument("--delay", type=float, default=0.8,
                         help="segundos entre requests (default 0.8, sé respetuoso)")
    parser.add_argument("--limit", type=int, default=None,
                         help="límite de artistas/discos a procesar (para pruebas)")
    args = parser.parse_args()

    t0 = time.time()
    if args.cmd in ("index", "all"):
        print("== Construyendo índice de artistas ==")
        build_artist_index(delay=args.delay)
    if args.cmd in ("artists", "all"):
        print("\n== Descargando fichas de artista ==")
        scrape_all_artists(delay=args.delay, limit=args.limit)
    if args.cmd in ("discs", "all"):
        print("\n== Descargando créditos de discos ==")
        scrape_all_discs(delay=args.delay, limit=args.limit)
    print(f"\nListo en {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
