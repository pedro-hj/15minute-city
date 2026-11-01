# Normalização de grades populacionais

O Cidade15 separa a **origem estatística** da **análise de acessibilidade**.
Uma CLI independente converte grades espaciais de órgãos nacionais em um
GeoPackage padronizado. O algoritmo, as métricas e o esquema PostgreSQL não mudam.
O formato IBGE/INSEE é identificado automaticamente pelas colunas dos dados;
`--profile` não é obrigatório.

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
  --input data/input/grade_id25.zip \
  --output data/normalized/brasil/grade_id25.gpkg
```

O detector reconhece IBGE pelas colunas `TOTAL` e `ID_UNICO`; o sinalizador `estimated` fica nulo,
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

Depois, normalize Lyon. O limite municipal é obtido automaticamente pelo OSMnx (requer acesso à internet):

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/france/filosofi2021.zip \
  --zip-member 'CAMINHO/INTERNO/DO_ARQUIVO.gpkg' \
  --city Lyon \
  --country France \
  --year 2021 \
  --output data/normalized/france/lyon_filosofi_2021.gpkg
```

O `--zip-member` é dispensável quando o ZIP contém somente um arquivo
geográfico. Se houver várias camadas no GeoPackage, use `--layer`.
O país é inferido quando a origem é reconhecida. O ano não pode ser
garantido apenas pelas colunas, então informe `--year 2021`.
O `--boundary caminho/lyon.geojson` continua disponível como alternativa
a `--city Lyon` para uso offline e recortes personalizados.

Na sequência, a CLI habitual analisa o resultado:

```bash
uv run fifteen-minute-city \
  --city Lyon \
  --country France \
  --pbf data/input/france-latest.osm.pbf \
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
GeoJSON ou ZIP com esses formatos), o programa também reconhece nomes comuns
como `population`, `residentes`, `residents`, `grid_id` e `cell_id`.
Quando não conseguir inferir um campo com segurança, configure somente as
colunas necessárias:

```bash
uv run fifteen-minute-city-normalize-population \
  --country Portugal \
  --source-name 'Instituto estatístico' \
  --year 2021 \
  --input data/input/portugal/grade.gpkg \
  --population-column residentes \
  --id-column id_celula \
  --output data/normalized/portugal/grade.gpkg
```

Use `--estimated-column` quando existir indicador de imputação 0/1;
`--city` (e `--state` quando necessário) para obter o limite municipal;
`--boundary` para fornecer um limite local em vez de geocodificar;
`--layer` e `--zip-member` para selecionar uma fonte espacial; e
`--overwrite` para substituir arquivos já existentes. `--profile` continua
aceito como opção para escolher explicitamente uma fonte conhecida.
Em caso de campos desconhecidos ou ambíguos, o programa informa os nomes
disponíveis e pede `--population-column` ou `--id-column` sem adivinhar.

A normalização exige geometria e CRS válido; `--city` apenas identifica a
região, não produz dados populacionais. Padronização técnica não garante
equivalência estatística entre os institutos.

CSV sem geometria não é aceito; é necessário primeiro associar seus registros
a células com geometria (por exemplo, realizando uma junção com uma grade).

## Etapas e limites

1. Esta entrega inclui reconhecimento automático IBGE/INSEE, geocodificação por cidade, formato padronizado, validação e testes.
2. A próxima etapa será a validação ponta a ponta em Lyon com dados reais,
   conferindo totais e imputações, grafo, serviços, métricas, FMC1 e API.

BPE, outras grades e processamento nacional da França ficam fora deste
primeiro escopo.
