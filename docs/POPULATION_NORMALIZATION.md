# Normalização de grades populacionais

O Cidade15 separa a **origem estatística** da **análise de acessibilidade**.
Uma CLI independente converte grades espaciais de órgãos nacionais em um
GeoPackage padronizado. O algoritmo, as métricas e o esquema PostgreSQL não mudam.

## Contrato `cidade15-population-v1`

Cada registro representa uma célula geográfica com população positiva:

| Coluna | Significado |
| --- | --- |
| `grid_id` | identificador original da célula, preservado como texto |
| `population` | total de habitantes (pode ser fracionário em fontes estimadas) |
| `country` | país |
| `source` | instituição / conjunto de dados |
| `source_year` | ano de referência, quando conhecido |
| `estimated` | `1` = imputado, `0` = não imputado, `null` = informação indisponível |
| `longitude`, `latitude` | coordenadas WGS84 de um ponto interior representativo |
| `geometry` | geometria espacial original reprojetada para EPSG:4326 |

O arquivo `nome.metadata.json` registra procedência, CRS, quantidade de
células, população total e população situada em células sinalizadas como imputadas. O recorte por município considera
o ponto representativo de cada célula; **não há repartição proporcional entre
municípios quando uma célula atravessa a fronteira**, conforme a regra de
análise já existente.

O normalizador rejeita população negativa, não numérica, ausente ou infinita,
identificadores vazios/duplicados e arquivos sem sistema de referência espacial.
Não inventa população nem classifica células de origem desconhecida como
não estimadas.

## Brasil — IBGE

```bash
uv run fifteen-minute-city-normalize-population \
  --profile ibge \
  --input data/input/grade_id25.zip \
  --output data/normalized/brasil/grade_id25.gpkg
```

O perfil IBGE lê `TOTAL` e `ID_UNICO`; o sinalizador `estimated` fica nulo,
porque esse perfil não contém uma coluna equivalente. **A CLI continua
aceitando os ZIPs originais do IBGE**; normalizá-los é opcional.

## França — INSEE Filosofi 2021 (200 m)

A fonte oficial contém `idcar_200m` (ID), `ind` (habitantes) e
`i_est_200` (1 quando a célula foi imputada). Os formatos vetoriais
GeoPackage e Shapefile são suportados diretamente, inclusive dentro de ZIP.

Fonte: https://www.insee.fr/fr/statistiques/8735162

Para um ZIP que contenha múltiplas regiões (metrópole, Martinica e Reunião),
identifique o arquivo desejado:

```bash
unzip -Z1 data/input/france/filosofi2021.zip
```

Depois, normalize apenas Lyon, fornecendo o limite geográfico:

```bash
uv run fifteen-minute-city-normalize-population \
  --profile insee-filosofi-2021 \
  --input data/input/france/filosofi2021.zip \
  --zip-member 'CAMINHO/INTERNO/DO_ARQUIVO.gpkg' \
  --boundary data/input/france/lyon.geojson \
  --output data/normalized/france/lyon_filosofi_2021.gpkg
```

O argumento `--zip-member` é dispensável quando o ZIP contém somente uma
fonte espacial. Se houver várias camadas no GeoPackage, use `--layer`.

Na sequência, a CLI habitual analisa o resultado:

```bash
uv run fifteen-minute-city \
  --city Lyon \
  --country France \
  --pbf data/input/france-latest.osm.pbf \
  --boundary data/input/france/lyon.geojson \
  --population-grid data/normalized/france/lyon_filosofi_2021.gpkg \
  --population-column population \
  --population-id-column grid_id \
  --enable-db
```

O PBF precisa cobrir Lyon. O relatório de normalização informa a população das células sinalizadas como imputadas; é essencial considerar essa incerteza ao interpretar
resultados, especialmente em áreas pouco densas. O campo `ind` refere-se a indivíduos
contabilizados em domicílios fiscais, não necessariamente à população
residente total do recenseamento; não se deve tratar os dois totais como
equivalentes.

## Outros países

Para qualquer arquivo vetorial com geometria e CRS (GeoPackage, Shapefile,
GeoJSON ou ZIP com esses formatos), configure o mapeamento:

```bash
uv run fifteen-minute-city-normalize-population \
  --profile custom \
  --country Portugal \
  --source-name 'Instituto estatístico' \
  --year 2021 \
  --input data/input/portugal/grade.gpkg \
  --population-column residentes \
  --id-column id_celula \
  --output data/normalized/portugal/grade.gpkg
```

Use `--estimated-column` quando existir um indicador 0/1 de imputação,
`--boundary` para recorte municipal, `--layer` para camadas de GPKG,
`--zip-member` para arquivos ZIP com várias fontes e `--overwrite`
somente quando desejar substituir um resultado.

CSV sem geometria não é aceito; é necessário primeiro associar seus registros
a células com geometria (por exemplo, realizando uma junção com uma grade).

## Etapas e limites

1. Esta entrega inclui perfis IBGE/INSEE, formato padronizado, validação e testes.
2. A próxima etapa será a validação ponta a ponta em Lyon com dados reais,
   conferindo totais e imputações, grafo, serviços, métricas, FMC1 e API.

BPE, outras grades e processamento nacional da França ficam fora deste
primeiro escopo.
