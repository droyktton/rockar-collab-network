# 🎸 rockar-collab-network

**¿Quiénes son los verdaderos hubs del rock argentino?**

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
   discografías.
2. **Construcción del grafo** de colaboración, combinando dos señales:
   - Links entre artistas mencionados en sus propias biografías
   - Créditos compartidos de disco (ej: *"Charly García y Pedro Aznar"*)
3. **Análisis de red** con [NetworkX](https://networkx.org/): densidad,
   componentes conexas, clustering, hubs por grado / betweenness / PageRank,
   detección de comunidades.
4. **Visualización**: una imagen estática coloreada por comunidad y una red
   interactiva navegable en el browser (zoom, arrastre, tooltips).

## 📊 Ejemplo de salida

*(reemplazar con un screenshot de `network_static.png` o un GIF del HTML interactivo)*

## 🚀 Instalación

```bash
git clone https://github.com/tu-usuario/rockar-collab-network.git
cd rockar-collab-network
python3 -m pip install -r requirements.txt
```

## 🕸️ Uso

```bash
# 1) Armar el índice de artistas
python3 scraper.py index

# 2) Bajar fichas de artista y créditos de disco
python3 scraper.py artists
python3 scraper.py discs

# (o las tres etapas juntas)
python3 scraper.py all

# 3) Analizar el grafo
python3 analyze.py

# 4) Visualizar
python3 visualize.py --min-degree 2
```

Todo el detalle de opciones, tiempos esperados y cómo retomar una corrida
cortada está en [`USAGE.md`](USAGE.md) *(o el nombre que le hayas puesto al README técnico original)*.

## 📁 Qué genera

| Archivo | Contenido |
|---|---|
| `data/report.md` | Resumen de métricas: tamaño, densidad, hubs, comunidades |
| `data/nodes.csv` / `edges.csv` | Tablas planas con centralidades y pesos |
| `data/graph.gexf` / `.graphml` | El grafo, para abrir en [Gephi](https://gephi.org/) |
| `data/network_static.png` | Imagen coloreada por comunidad |
| `data/network_interactive.html` | Red navegable en el browser |

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

*Datos descargados en [fecha]. La enciclopedia sigue actualizándose, así que
una corrida posterior puede dar resultados distintos.*

## 📄 Licencia

El código de este repositorio se distribuye bajo licencia [MIT](LICENSE)
*(o la que prefieras)*. Los datos derivados de rock.com.ar se comparten con
fines de investigación; cualquier uso comercial debería consultarse con el
sitio fuente.

## 🛠️ Stack

Python · [NetworkX](https://networkx.org/) · [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) · [Matplotlib](https://matplotlib.org/) · [pyvis](https://pyvis.readthedocs.io/)

## 🤝 Créditos

- Idea, dirección del proyecto y ejecución: Ale Kolton
- Diseño de scraper, código de análisis de red y documentación:
  desarrollado con [Claude](https://claude.ai) (Anthropic)
