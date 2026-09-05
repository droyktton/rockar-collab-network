# 🎸 rockar-collab-network

**¿Quiénes son los verdaderos hubs del rock argentino?**

**[👉 Explorá la red interactiva](https://droyktton.github.io/rockar-collab-network/)**

Este proyecto descarga datos de [rock.com.ar](https://rock.com.ar) —la enciclopedia
del rock argentino online desde 1996— y construye la **red de colaboración**
entre artistas: quién grabó con quién, quién integró qué banda, quién aparece
mencionado junto a quién. Sobre esa red se calculan métricas de teoría de
grafos (hubs, comunidades, centralidad) y se generan visualizaciones para
explorarla.

> Proyecto de análisis de datos independiente. Sin afiliación con rock.com.ar.

---

## ✨ Qué hace

1. **Scraping respetuoso** de la enciclopedia (con caché en disco y rate
   limiting) para armar el índice completo de artistas, sus biografías y
   discografías — **5.778 artistas** en la corrida completa.
2. **Construcción del grafo** de colaboración, combinando dos señales:
   - Links entre artistas mencionados en sus propias biografías
   - Créditos compartidos de disco (ej: *"Charly García y Pedro Aznar"*)
3. **Análisis de red** con [NetworkX](https://networkx.org/): densidad,
   componentes conexas, clustering, hubs por grado / betweenness / PageRank,
   detección de comunidades.
4. **Visualización**, en cuatro formas distintas:
   - Red completa interactiva (navegable en el browser)
   - Línea de tiempo (año de debut vs. conexiones, por comunidad)
   - Mapa de calor de actividad discográfica por comunidad y década
   - Ego-networks de artistas puntuales (su vecindario directo, sin ruido)

## 🔍 Algunos hallazgos

- **Charly García** encabeza la comunidad más grande de la red (265 artistas
  más) y es la más activa en casi todas las décadas — el nodo más central
  por lejos.
- La comunidad de **Gustavo Santaolalla** recién se vuelve dominante en los
  2000s-2010s, coincidiendo con su rol como productor de una nueva
  generación (Bajofondo, bandas de sonido) más que con su carrera como
  artista de los 70s-80s.
- La comunidad de **Cielo Razzo** aparece únicamente a partir de los 2010s
  — la fecha real de formación de la banda —, una buena señal de que la
  detección de comunidades está capturando estructura real y no ruido.
- El grado (cantidad de colaboraciones documentadas) cae fuerte para los
  artistas que debutaron después de 2010. Es tentador leer esto como
  "el rock viejo conectaba más gente", pero es más probable que sea un
  **efecto de acumulación**: un artista que debutó en 1970 tuvo 50 años
  para sumar colaboraciones documentadas; uno que debutó en 2018, apenas
  unos pocos. También puede influir que la cobertura editorial de la
  enciclopedia sea más profunda para las figuras clásicas.

## 📁 Qué genera

| Archivo | Contenido |
|---|---|
| `data/report.md` | Resumen de métricas: tamaño, densidad, hubs, comunidades |
| `data/nodes.csv` / `edges.csv` | Tablas planas con centralidades y pesos |
| `data/graph.gexf` / `.graphml` | El grafo, para abrir en [Gephi](https://gephi.org/) |
| `data/network_static.png` | Imagen coloreada por comunidad |
| `data/network_interactive.html` | Red completa navegable en el browser |
| `data/timeline_interactive.html` | Año de debut vs. grado, por comunidad |
| `data/heatmap_comunidad_decada.png` | Actividad discográfica por comunidad/década |
| `data/ego_<artista>.png` / `.html` | Red de colaboración de un artista puntual |

## 🚀 Instalación

```bash
git clone https://github.com/droyktton/rockar-collab-network.git
cd rockar-collab-network
python3 -m pip install -r requirements.txt
```

## 🕸️ Uso

```bash
# 1) Armar el índice de artistas
python3 scraper.py index

# 2) Bajar fichas de artista y créditos de disco (incluye año de edición)
python3 scraper.py artists
python3 scraper.py discs

# (o las tres etapas juntas)
python3 scraper.py all

# 3) Analizar el grafo
python3 analyze.py

# 4) Visualizar
python3 visualize.py --min-degree 2                          # red completa
python3 timeline.py --min-degree 2 --top-communities 10        # línea de tiempo
python3 heatmap.py --top-communities 10                        # mapa de calor
python3 ego_network.py "Charly Garcia" --hops 1                # ego-network
```

Todo el detalle de opciones, tiempos esperados y cómo retomar una corrida
cortada está en [`USAGE.md`](USAGE.md).

## 🧠 Metodología y criterio de conexión

Dos artistas quedan conectados si:
- La biografía de uno **linkea** al otro (colaboración, integrante de banda, proyecto paralelo), o
- Aparecen **acreditados juntos** en la ficha de un mismo disco

⚠️ **Los nodos mezclan personas y bandas** sin distinguirlos (así están
modelados en la enciclopedia original), así que una arista puede representar
persona↔persona, persona↔banda o banda↔banda. Tenelo en cuenta al leer los
rankings de hubs: una banda longeva con mucha rotación de miembros puede
tener un grado alto sin que eso hable de una sola persona particularmente
conectada.

La red refleja **colaboración documentada en rock.com.ar**, no
necesariamente toda colaboración real existente — es tan completa como la
propia enciclopedia.

## 🙏 Fuente y agradecimientos

Todos los datos (biografías, discografías, relaciones entre artistas) fueron
extraídos de **[rock.com.ar](https://rock.com.ar)**. Todo el crédito por el
contenido original es de su equipo editorial. Este repositorio comparte
únicamente el **código de análisis** y **datos derivados** (nombres, slugs,
relaciones estructuradas) para fines de investigación y visualización de
redes — no reproduce el contenido editorial del sitio (biografías completas,
textos, etc.).

Si este proyecto te resultó interesante, la mejor forma de agradecer es
visitar [rock.com.ar](https://rock.com.ar) y explorar las fichas originales
de los artistas que aparecen en la red.

*Datos descargados en septiembre de 2026. La enciclopedia sigue
actualizándose, así que una corrida posterior puede dar resultados distintos.*

## 🤝 Créditos

- Idea, dirección del proyecto y ejecución: Ale Kolton
- Scraper, análisis de red, visualizaciones y esta página: desarrollados
  con [Claude](https://claude.ai) (Anthropic)
  
## 📄 Licencia

El código de este repositorio se distribuye bajo licencia [MIT](LICENSE).
Los datos derivados de rock.com.ar se comparten con fines de investigación;
cualquier uso comercial debería consultarse con el sitio fuente.

## 🛠️ Stack

Python · [NetworkX](https://networkx.org/) · [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) · [Matplotlib](https://matplotlib.org/) · [pyvis](https://pyvis.readthedocs.io/) · [Plotly](https://plotly.com/python/)
