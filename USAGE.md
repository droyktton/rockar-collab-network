# Guía de uso técnica

Instalación paso a paso, opciones de cada script, tiempos esperados y cómo
retomar una corrida cortada. Para la visión general del proyecto y los
hallazgos, ver el [README](README.md).

## Instalación

```bash
git clone https://github.com/droyktton/rockar-collab-network.git
cd rockar-collab-network
python3 -m pip install -r requirements.txt
```

Si tu sistema no tiene `pip` o da error de repositorios (por ejemplo en una
distribución de Linux vieja), instalalo primero con `sudo apt install
python3-pip`, o si tus repos de apt están rotos, apuntalos a
`old-releases.ubuntu.com` antes.

## 1. Armar el índice de artistas

```bash
python3 scraper.py index
```

Recorre `/enciclopedia/` → `/abc/{letra}/` (con paginación) y arma la lista
completa de artistas. Es rápido — no baja fichas individuales todavía.

## 2. Bajar fichas de artista y créditos de disco

```bash
python3 scraper.py artists    # biografías + discografía de cada artista
python3 scraper.py discs      # créditos y año de edición de cada disco único
# o las dos juntas:
python3 scraper.py all
```

Recomendado: probar primero con una muestra chica antes de la corrida completa.

```bash
python3 scraper.py artists --limit 50
python3 scraper.py discs --limit 100
```

### Tiempos esperados (corrida completa, ~5.778 artistas)

- `artists`: con el delay por defecto (0.8s), del orden de **1h15min** de
  puro delay, más el tiempo real de descarga.
- `discs`: depende de cuántos discos únicos aparezcan (varios miles). Puede
  tardar **3-5 horas**.

Para dejarlo corriendo de fondo:

```bash
nohup python3 scraper.py all > scraper.log 2>&1 &
tail -f scraper.log        # ver progreso en vivo (Ctrl+C solo corta el tail)
ps aux | grep scraper.py   # confirmar que sigue vivo
```

### Si se corta a mitad de camino

No pasa nada — tanto `cache/` (HTML crudo) como `data/artists.json` /
`data/disc_credits.json` guardan progreso incremental. Volvé a correr el
mismo comando y retoma donde quedó, sin volver a bajar lo ya cacheado.

## 3. Analizar el grafo

```bash
python3 analyze.py
```

Construye el grafo combinando menciones de biografía y créditos de disco,
calcula métricas (densidad, componentes, clustering, hubs por
grado/betweenness/PageRank, comunidades) y exporta `data/report.md`,
`data/nodes.csv`, `data/edges.csv`, `data/graph.gexf`, `data/graph.graphml`.

## 4. Visualizar

```bash
python3 visualize.py --min-degree 2
```
Genera `data/network_static.png` (imagen coloreada por comunidad) y
`data/network_interactive.html` (navegable en el browser, sin depender de
carpetas externas — es autocontenido). `--min-degree` oculta nodos muy
periféricos para que el dibujo no se sature.

```bash
python3 timeline.py --min-degree 2 --top-communities 10
```
Scatter interactivo: año de debut de cada artista vs. su grado, coloreado
por comunidad. `--top-communities` agrupa las comunidades chicas en "Otras"
para que la leyenda de colores sea legible.

```bash
python3 heatmap.py --top-communities 10
```
Mapa de calor de actividad discográfica (comunidad × década).

```bash
python3 ego_network.py "Charly Garcia" --hops 1
python3 ego_network.py "Charly Garcia" --hops 2 --min-degree 2
```
Red de colaboración de un artista puntual: él mismo, sus colaboradores
directos (`--hops 1`) o también los colaboradores de sus colaboradores
(`--hops 2`). Acepta nombre parcial; si hay ambigüedad, lista las
coincidencias para que seas más específico.

## Sobre el scraping responsable

- Revisá `https://rock.com.ar/robots.txt` y sus términos legales antes de
  lanzar una corrida completa.
- El `delay` por defecto (0.8s) y la caché en disco están puestos a
  propósito para minimizar la carga sobre el sitio. Si vas a compartir
  públicamente el dataset o el análisis, es buena práctica citar a
  rock.com.ar como fuente (ver el README).
- Si el sitio cambia de estructura en el futuro, lo primero que vas a notar
  es que `artist_index.json` queda vacío o muy chico — revisá los
  selectores en `scraper.py` (`ARTIST_URL_RE`, `DISC_URL_RE`, `YEAR_LABELS`)
  contra el HTML actual.

## Limitaciones a tener en cuenta al interpretar los resultados

- La red mide **menciones de colaboración documentadas en rock.com.ar**, no
  colaboraciones reales exhaustivas — es tan completa como la enciclopedia.
- Los nodos mezclan personas y bandas sin distinguirlos (ver el README).
- El matching de nombres en créditos de disco es heurístico (normaliza
  acentos/mayúsculas pero puede fallar con apodos, "Los X" vs "X", etc.).
  Revisá `nodes.csv` para nodos "externos" (slugs sin ficha propia) que
  puedan ser errores de resolución.
- El año de cada disco se extrae con patrones de texto (`YEAR_LABELS` en
  `scraper.py`); en la corrida completa, ~99.98% de los discos obtuvieron
  un año detectado, pero vale la pena revisar casos puntuales si algo se ve
  raro en el timeline o el heatmap.
- El diámetro/camino promedio se omite automáticamente si la componente
  principal es muy grande (>3000 nodos), porque el cálculo exacto es
  costoso; ese caso queda anotado en `report.md`.
