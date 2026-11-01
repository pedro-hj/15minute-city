# Normalizador de grades populacionais

O normalizador recebe **um arquivo geográfico e o nome de duas colunas**.
Ele gera um GeoPackage com três campos padronizados:

| Campo | Significado |
| --- | --- |
| `ID` | Identificador único da quadrícula, preservado como texto |
| `LOCATION` | Geometria original (ponto ou polígono) |
| `POPULATION` | Número de habitantes da quadrícula |

A geometria é encontrada automaticamente pelo GeoPandas. O CRS original é
**preservado**. Não há identificação automática de país, alteração de população
ou recorte municipal.

## Exemplo: França (INSEE)

Extraia a pasta `france_metro` do ZIP original, mantendo os arquivos
`.shp`, `.dbf`, `.shx` e `.prj` juntos.

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/france/france_metro/carreaux_200m_met.shp \
  --id-column idcar_200m \
  --population-column ind \
  --output data/normalized/france.gpkg
```

## Exemplo: outra grade (IBGE ou outro país)

Substitua os nomes de colunas pelos nomes reais do arquivo.

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/brasil/grade.gpkg \
  --id-column CODIGO \
  --population-column HABITANTES \
  --output data/normalized/brasil.gpkg
```

Os exemplos usam formatos vetoriais que o GeoPandas consegue ler, como
Shapefile, GeoPackage e GeoJSON. O comando não interpreta CSV sem geometria
nem escolhe automaticamente arquivos dentro de ZIPs com várias camadas.

Se faltar uma coluna, se o CRS estiver ausente, ou se houver ID vazio/repetido,
população inválida/negativa ou geometria vazia, o programa informa o erro.
Arquivos existentes não são sobrescritos.

## Uso na CLI principal

O mesmo arquivo normalizado pode ser utilizado para diversas cidades;
a **CLI principal** recorta as quadrículas do município e reprojeta
geometrias quando necessário para associá-las à rede caminhável.

```bash
uv run fifteen-minute-city \
  --city Lyon \
  --country France \
  --pbf data/input/france.osm.pbf \
  --population-grid data/normalized/france.gpkg \
  --population-id-column ID \
  --population-column POPULATION
```

No GeoPackage, o nome físico do campo espacial é `LOCATION`; ao ler com
GeoPandas ele pode aparecer como `geometry`, sem perda de informação.
