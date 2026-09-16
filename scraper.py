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


# Selectores típicos de WordPress para el cuerpo del artículo. Se prueban en
# orden; el primero que devuelva contenido gana. Esto es importante para no
# buscar menciones en el sidebar ("Notas relacionadas", menús, etc.), que
# también contienen texto libre y podrían generar falsos positivos.
CONTENT_SELECTORS = [
    "article", ".entry-content", ".post-content", ".single-content", "main",
]


def _extract_bio_text(soup) -> str:
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 200:
            return node.get_text(" ", strip=True)
    # respaldo: toda la página. Menos preciso (puede incluir sidebar/menú),
    # pero mejor que no detectar nada si el sitio no usa ninguno de los
    # selectores de arriba.
    return soup.get_text(" ", strip=True)


def _extract_bio_node(soup):
    """Igual que _extract_bio_text pero devuelve el nodo del DOM (no el
    texto plano), para poder ubicar los <a> dentro de él y mirar su
    contexto local exacto en el árbol HTML."""
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 200:
            return node
    return soup


# Frases que indican que dos artistas comparten sólo un mismo evento/cartel
# (festival, gira con muchos actos), no necesariamente colaboración musical
# real. Ej: "también estuvieron INXS, Nina Hagen, ... y Sumo, entre otros"
# — el sitio linkea a todos los mencionados, pero eso no implica que hayan
# tocado juntos ni que exista relación musical directa entre ellos.
EVENT_CONTEXT_KEYWORDS_RAW = [
    "festival", "cartel", "line up", "lineup", "tambien estuvieron",
    "tambien actuaron", "entre otros", "se presentaron", "compartieron escenario",
    "comparte cartel", "compartio cartel", "coincidieron en", "mismo escenario",
]


def _split_sentences(text: str):
    """Separador simple de oraciones: corta después de . ! ? seguido de
    espacio. No es perfecto (no maneja abreviaturas como 'Sr.'), pero
    alcanza para distinguir hechos distintos dentro del mismo párrafo."""
    return re.split(r"(?<=[.!?])\s+", text)


def classify_bio_links(soup, self_slug: str):
    """Separa los links reales de biografía (<a href> a otros artistas) en
    dos grupos, mirando el texto de la ORACIÓN donde vive cada link (no
    todo el párrafo — un párrafo puede mezclar un hecho de "evento
    compartido" con una colaboración real distinta en otra oración; usar
    todo el párrafo contaminaría la segunda con la palabra clave de la
    primera):
      - kept: se mantienen como bio_links (colaboración real presumible)
      - evento: el contexto sugiere que sólo comparten un mismo evento/cartel
        (festival, gira con muchos actos) — se guardan aparte, no entran al
        grafo por default.

    A diferencia del filtro de menciones en texto plano (que inventa la
    heurística de cero), acá el link YA lo puso el sitio; sólo estamos
    re-clasificando su intención probable según el contexto inmediato.
    """
    node = _extract_bio_node(soup)
    kept, evento = [], []
    seen = set()
    keywords_norm = [normalize_name(k) for k in EVENT_CONTEXT_KEYWORDS_RAW]

    for a in node.find_all("a", href=True):
        m = ARTIST_URL_RE.match(_abs_url(a["href"]))
        if not m or m.group(1) == self_slug:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)

        block = a.find_parent(["p", "li", "div"]) or a.parent
        block_text = block.get_text(" ", strip=True) if block else ""
        anchor_text = a.get_text(strip=True)

        # ubicar en qué oración específica del párrafo cae este link; si
        # no se puede determinar (caso raro), usar el párrafo completo
        # como respaldo conservador
        context_text = block_text
        if anchor_text:
            for sent in _split_sentences(block_text):
                if anchor_text in sent:
                    context_text = sent
                    break

        context_norm = normalize_name(context_text)
        if any(kw in context_norm for kw in keywords_norm):
            evento.append(slug)
        else:
            kept.append(slug)

    return sorted(set(kept)), sorted(set(evento))


def rescan_bio_link_context(limit=None):
    """Reprocesa las páginas de artista YA CACHEADAS (no genera ningún
    request nuevo) para re-clasificar los bio_links existentes: separa los
    que probablemente sean colaboración real de los que sólo reflejan haber
    compartido un mismo evento/festival (ver EVENT_CONTEXT_KEYWORDS_RAW).

    Actualiza 'bio_links' (ahora filtrado) y agrega 'bio_links_evento'
    (excluido del grafo por default, pero disponible para inspección)."""
    artists = load_json(DATA_DIR / "artists.json", {})
    if not artists:
        print("No hay artists.json. Corré primero 'scraper.py artists'.")
        sys.exit(1)

    slugs = list(artists.keys())
    if limit:
        slugs = slugs[:limit]

    total_movidos = 0
    for i, slug in enumerate(slugs, 1):
        info = artists[slug]
        try:
            html = fetch(info["url"])  # cacheado, no genera request real
        except Exception as e:
            print(f"  ! error en {slug}: {e}")
            continue
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        kept, evento = classify_bio_links(soup, self_slug=slug)
        info["bio_links"] = kept
        info["bio_links_evento"] = evento
        total_movidos += len(evento)
        if i % 500 == 0 or i == len(slugs):
            save_json(artists, DATA_DIR / "artists.json")
            print(f"  {i}/{len(slugs)} biografías re-clasificadas "
                  f"({total_movidos} links movidos a 'evento compartido' hasta ahora)")

    save_json(artists, DATA_DIR / "artists.json")
    print(f"\nListo: {total_movidos} links re-clasificados como 'evento compartido' "
          f"(sacados de bio_links, guardados en bio_links_evento).")


# Algunos artistas de la enciclopedia tienen nombres que también son frases
# genéricas muy comunes en español ("la banda", "buenos aires"), que
# aparecen todo el tiempo en cualquier biografía SIN referirse a ese artista
# en particular. Esto infla artificialmente sus menciones muy por encima de
# cualquier hub real (se detectó porque aparecían con 10x+ el conteo del
# siguiente hub genuino). Los excluimos de la detección de menciones en
# texto plano; igual pueden aparecer en el grafo vía bio_links reales o
# créditos de disco, sin problema.
#
# Se excluye por NOMBRE normalizado (no por slug): la enciclopedia tiene
# varias entradas distintas con el mismo nombre exacto quando hay bandas
# homónimas (ej. "El Resto", "El Resto (2)", etc. -> slugs el-resto,
# el-resto-2, el-resto-3...). Si excluyéramos sólo un slug puntual, la
# colisión simplemente reaparece en el próximo duplicado con el mismo
# nombre. Excluir por nombre cubre todos los duplicados de una sola vez.
STOPLIST_NAMES_RAW = [
    "la banda",       # frase genérica "la banda de X", no un artista específico
    "buenos aires",   # nombre de la ciudad, mencionado en casi toda bio
    "la costa",       # frase genérica geográfica ("gira por la costa")
    "la mezcla",      # término técnico de grabación ("la mezcla del disco")
    "la data",        # jerga genérica ("no tengo la data exacta")
    "de juan",        # colisiona con "de Juan [Carlos Baglietto, etc]" — la
                       # preposición "de" + cualquier "Juan ___", no un artista
    "el resto",       # colisiona con la frase genérica "el resto de los
                       # integrantes/músicos", no el/los artista(s) reales
                       # con ese nombre (hay varios duplicados: el-resto,
                       # el-resto-2, el-resto-3...)
]


def _build_full_name_lookup(index: dict, min_name_length: int = 6, stoplist_names=None):
    """Mapa nombre_completo_normalizado -> slug, para detectar menciones en
    texto libre. A diferencia de _build_name_lookup (que también acepta
    nombres cortos, pensado para resolver créditos de disco ya acotados),
    acá exigimos:
      - al menos dos palabras (evita falsos positivos de artistas con
        nombre artístico de una sola palabra común, ej. si alguien se hace
        llamar "Sol" o "Rey")
      - largo mínimo razonable
      - que el nombre normalizado no esté en la lista de exclusión
        (STOPLIST_NAMES_RAW) — cubre automáticamente todos los artistas
        homónimos con ese nombre, no sólo un slug puntual
    para minimizar falsos positivos al buscar en biografías completas."""
    stoplist_norm = {normalize_name(n) for n in
                      (stoplist_names if stoplist_names is not None else STOPLIST_NAMES_RAW)}
    lookup = {}
    for slug, info in index.items():
        norm = normalize_name(info["name"])
        if norm in stoplist_norm:
            continue
        if len(norm) >= min_name_length and " " in norm:
            lookup[norm] = slug
    return lookup


# Palabras/raíces que indican colaboración real (no mera influencia o
# admiración) cerca de un nombre mencionado. Se buscan como substring ya
# normalizado (sin acentos, minúsculas) dentro de una ventana de texto
# alrededor de cada mención. Esto separa "grabó junto a X" (colaboración)
# de "tuvo como influencia a X" (inspiración, no colaboración real).
COLLAB_CONTEXT_KEYWORDS_RAW = [
    "grabo", "grabaron", "grabando",
    "toco", "tocaron", "tocando",
    "particip", "integrante", "invitad", "convocad", "acompano", "colabor",
    "banda de", "productor", "produjo", "produccion",
    "arregl", "junto a", "junto con",
    "musico de", "bajista de", "guitarrista de", "baterista de",
    "tecladista de", "violinista de", "vientos de", "coros de", "coro de",
    "featuring", "dueto con", "duo con",
    "telonero de", "telonera de", "gira de", "gira con",
    "fundadora", "fundador", "fundaron", "reemplazo",
]
# Palabras ambiguas: sólo cuentan como contexto de colaboración si ADEMÁS
# aparece un sustantivo de agrupación musical cerca (ver MUSICAL_GROUP_NOUNS).
# "integrado"/"integrada" es el caso típico: "trío integrado por X" es
# colaboración real, pero "jurado integrado por X" no tiene nada que ver
# con música — la palabra sola no alcanza para distinguirlos.
AMBIGUOUS_CONTEXT_KEYWORDS_RAW = [
    "integrado", "integrada", "integrando", "integraron",
    "compuesta", "compuesto", "compusieron",
    "conformada", "conformado", "conformaban", "conformaron",
]
MUSICAL_GROUP_NOUNS_RAW = [
    "banda", "trio", "grupo", "dueto", "duo", "cuarteto", "conjunto",
    "orquesta", "ensamble", "quinteto", "sexteto", "combo",
]
CONTEXT_WINDOW_CHARS = 100

# Patrón directo "Nombre en <instrumento>" — muy común en listas de
# formación de banda ("Marcelo Torres en bajo, Hernán Arramberri en
# batería..."). Es una señal fuerte por sí sola: no depende de estar cerca
# de una palabra como "compuesta por", que en listas largas puede quedar
# lejos de los últimos nombres enumerados.
INSTRUMENT_WORDS_RAW = [
    "bajo", "guitarra", "guitarras", "bateria", "teclado", "teclados",
    "voz", "voces", "coro", "coros", "saxo", "saxofon", "trompeta",
    "trombon", "violin", "percusion", "vientos", "sintetizador",
    "sintetizadores", "flauta", "acordeon", "charango", "bombo",
    "contrabajo", "piano",
]


def find_mentioned_artists(bio_text: str, full_name_lookup: dict, self_slug: str):
    """Busca nombres completos de otros artistas mencionados como texto
    plano (sin link) dentro de una biografía, exigiendo que haya una palabra
    de colaboración cerca del nombre (ver COLLAB_CONTEXT_KEYWORDS_RAW) para
    distinguir colaboración real de una simple mención de influencia
    ("tuvo como influencia a X" no cuenta; "grabó junto a X" sí).

    Palabras ambiguas como "integrado"/"compuesta" sólo cuentan si además
    hay un sustantivo de agrupación musical cerca (ver
    AMBIGUOUS_CONTEXT_KEYWORDS_RAW y MUSICAL_GROUP_NOUNS_RAW) — así "trío
    integrado por X" cuenta pero "jurado integrado por X" no.

    También reconoce directamente el patrón "Nombre en <instrumento>"
    (ver INSTRUMENT_WORDS_RAW), típico de listas de formación de banda,
    sin depender de la distancia a otras palabras clave.

    Devuelve (con_contexto, sin_contexto): la primera lista es la que se usa
    para el grafo; la segunda se guarda aparte sólo para inspección/debug.
    """
    keywords_norm = [normalize_name(k) for k in COLLAB_CONTEXT_KEYWORDS_RAW]
    ambiguous_norm = [normalize_name(k) for k in AMBIGUOUS_CONTEXT_KEYWORDS_RAW]
    group_nouns_norm = [normalize_name(k) for k in MUSICAL_GROUP_NOUNS_RAW]
    instruments_norm = [normalize_name(k) for k in INSTRUMENT_WORDS_RAW]
    norm_text = f" {normalize_name(bio_text)} "

    con_contexto, sin_contexto = [], []
    for name_norm, slug in full_name_lookup.items():
        if slug == self_slug:
            continue
        needle = f" {name_norm} "
        start = 0
        found_any = False
        found_context = False
        while True:
            idx = norm_text.find(needle, start)
            if idx == -1:
                break
            found_any = True

            # patrón directo "Nombre en <instrumento>": mirar sólo los ~20
            # caracteres inmediatamente después del nombre
            after = norm_text[idx + len(needle): idx + len(needle) + 20]
            if after.startswith("en ") and any(
                    after[3:3 + len(instr)] == instr for instr in instruments_norm):
                found_context = True
                break

            window = norm_text[max(0, idx - CONTEXT_WINDOW_CHARS):
                                idx + len(needle) + CONTEXT_WINDOW_CHARS]
            if any(kw in window for kw in keywords_norm):
                found_context = True
                break
            if (any(kw in window for kw in ambiguous_norm)
                    and any(g in window for g in group_nouns_norm)):
                found_context = True
                break
            start = idx + 1
        if found_context:
            con_contexto.append(slug)
        elif found_any:
            sin_contexto.append(slug)

    return sorted(set(con_contexto)), sorted(set(sin_contexto))


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


def rescan_bio_mentions(min_name_length=6, limit=None):
    """Reprocesa las páginas de artista YA CACHEADAS (no genera ningún
    request nuevo) para detectar menciones en texto plano a otros artistas
    que no estaban linkeadas — por ejemplo, músicos de sesión mencionados
    por nombre pero sin hipervínculo en la biografía de la estrella.

    Agrega el campo 'mentioned_slugs' a cada entrada de artists.json,
    separado de 'bio_links' (que sigue siendo sólo links reales) para que
    la procedencia de cada conexión quede trazable en edges.csv."""
    index = load_json(DATA_DIR / "artist_index.json")
    artists = load_json(DATA_DIR / "artists.json", {})
    if not index or not artists:
        print("Faltan artist_index.json / artists.json. Corré primero "
              "'index' y 'artists'.")
        sys.exit(1)

    full_lookup = _build_full_name_lookup(index, min_name_length=min_name_length)
    print(f"Nombres completos aptos para detección de menciones: {len(full_lookup)} "
          f"de {len(index)} (se excluyen nombres de una sola palabra o muy cortos)")

    slugs = list(artists.keys())
    if limit:
        slugs = slugs[:limit]

    updated = 0
    total_mentions_found = 0
    total_weak_found = 0
    for i, slug in enumerate(slugs, 1):
        info = artists[slug]
        try:
            html = fetch(info["url"])  # ya está cacheado, esto no genera request real
        except Exception as e:
            print(f"  ! error en {slug}: {e}")
            continue
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        bio_text = _extract_bio_text(soup)
        con_contexto, sin_contexto = find_mentioned_artists(bio_text, full_lookup, self_slug=slug)
        # no duplicar lo que ya está como link real
        already_linked = set(info.get("bio_links", []))
        new_mentions = sorted(set(con_contexto) - already_linked)
        weak_mentions = sorted(set(sin_contexto) - already_linked - set(new_mentions))
        info["mentioned_slugs"] = new_mentions
        info["mentioned_slugs_weak"] = weak_mentions  # sólo para inspección, no se usa en el grafo
        total_mentions_found += len(new_mentions)
        total_weak_found += len(weak_mentions)
        updated += 1
        if i % 200 == 0 or i == len(slugs):
            save_json(artists, DATA_DIR / "artists.json")
            print(f"  {i}/{len(slugs)} biografías re-escaneadas "
                  f"({total_mentions_found} con contexto de colaboración, "
                  f"{total_weak_found} sin contexto -descartadas del grafo-)")

    save_json(artists, DATA_DIR / "artists.json")
    print(f"\nListo: {updated} artistas re-escaneados.")
    print(f"  {total_mentions_found} menciones CON contexto de colaboración "
          f"(se usan en el grafo, campo 'mentioned_slugs')")
    print(f"  {total_weak_found} menciones SIN contexto claro "
          f"(guardadas en 'mentioned_slugs_weak' sólo para inspección, "
          f"no se usan en el grafo)")

    # Diagnóstico automático: si algún nombre aparece mencionado por una
    # cantidad de artistas DISTINTOS sospechosamente alta, probablemente sea
    # una colisión con una frase genérica del español (como pasó con
    # "la banda" / "buenos aires"), no un hub real. Un hub genuino puede
    # tener grado alto, pero rara vez es 5-10x más que el siguiente.
    from collections import Counter
    mention_counts = Counter()
    for info in artists.values():
        for slug in info.get("mentioned_slugs", []):
            mention_counts[slug] += 1
    if mention_counts:
        top = mention_counts.most_common(8)
        threshold = top[0][1]
        segundo = top[1][1] if len(top) > 1 else 0
        if threshold > 3 * max(segundo, 1) and threshold > 50:
            print(f"\n⚠️  POSIBLE COLISIÓN DE NOMBRE GENÉRICO:")
            print(f"   '{top[0][0]}' aparece mencionado por {threshold} artistas distintos, "
                  f"muy por encima del siguiente ({segundo}). Si no es un hub real "
                  f"conocido, agregalo a STOPLIST_NAMES_RAW en scraper.py y volvé a "
                  f"correr 'scraper.py mentions'.")
        print("\nTop 8 nombres más mencionados (revisar si tiene sentido):")
        for slug, n in top:
            name = artists.get(slug, {}).get("name", slug)
            print(f"   {name} ({slug}): mencionado por {n} artistas distintos")


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
    parser.add_argument("cmd", choices=["index", "artists", "discs", "mentions", "bio-context", "all"])
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
    if args.cmd == "mentions":
        # No forma parte de "all" a propósito: es una detección basada en
        # texto libre (más ruidosa que links/créditos), conviene correrla
        # aparte y revisar los resultados antes de sumarlos al análisis.
        print("== Re-escaneando biografías cacheadas por menciones en texto plano ==")
        rescan_bio_mentions(limit=args.limit)
    if args.cmd == "bio-context":
        # Tampoco forma parte de "all": re-clasifica los bio_links YA
        # existentes, separando colaboración real de "mismo evento/festival".
        print("== Re-clasificando bio_links por contexto (colaboración vs. evento compartido) ==")
        rescan_bio_link_context(limit=args.limit)
    print(f"\nListo en {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
