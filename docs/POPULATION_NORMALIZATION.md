# Normalizador universal de grades populacionais

O normalizador do Cidade15 **não depende de país nem de instituto estatístico**.
Ele converte dados populacionais espaciais para um contrato fixo, com apenas
três campos:

| Campo | Significado | Tipo |
| --- | --- | --- |
| `ID` | identificador da célula; original quando disponível, gerado caso contrário | texto |
| `LOCALIZACAO` | geometria da célula ou ponto populacional, em EPSG:4326 | espacial (GeoPackage) |
| `POPULACAO` | quantidade de pessoas representadas pela unidade espacial | numérico >= 0 |

O GeoPackage possui ainda o identificador técnico `fid` exigido pelo formato,
mas o contrato de atributos da aplicação é apenas `ID`, `LOCALIZACAO`,
`POPULACAO`. Por padrão, o GeoPandas apresenta a geometria lida com o nome
`geometry`; o campo geométrico **dentro do GeoPackage** chama-se
`LOCALIZACAO`.

O formato de saída é GeoPackage (`.gpkg`) com a camada
`grade_populacional`. Um arquivo `*.metadata.json` separado registra origem,
campos detectados, CRS original, recorte e totais, **sem poluir os três campos
normalizados**.

## Como o normalizador trabalha

1. Detecta o formato do arquivo de entrada (GPKG, SHP, GeoJSON, CSV ou ZIP).
2. Utiliza a geometria espacial original ou cria pontos a partir de
   latitude/longitude. CSV com WKT também é aceito mediante CRS informado.
3. Identifica colunas de ID e população por uma lista **genérica** de nomes
   frequentes (`ID_UNICO`, `idcar_200m`, `grid_id`, `POPULACAO`, `ind`,
   `TOTAL`, `residents`, etc.).
4. **Se houver ambiguidade, interrompe** e informa os campos disponíveis.
   Não utiliza números aleatórios de outras colunas como habitantes.
5. Valida a presença da geometria, CRS, população numérica e não negativa,
   identificadores únicos quando fornecidos.
6. Se solicitado, recorta a grade pela cidade (`--city`) ou por limite local
   (`--boundary`). O ponto representativo de cada célula deve estar dentro
   do limite. Não divide população proporcionalmente em células de fronteira.
7. Grava `ID`, `LOCALIZACAO` e `POPULACAO` em EPSG:4326.

**Importante:** o programa padroniza a **estrutura dos dados**, não a definição
estatística de população. Diferentes órgãos podem medir populações distintas.
Essa informação deve ser documentada na metodologia do TCC.

## Exemplo: qualquer grade vetorial

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/grade.zip \
  --output data/normalized/grade.gpkg
```

Esse comando funciona sem escolher o país ou a instituição, desde que o ZIP
contenha uma fonte vetorial e que as colunas possam ser identificadas com
segurança. Arquivos `.gpkg`, `.shp` e `.geojson` também podem ser informados
diretamente.

Se o ZIP contiver mais de uma fonte espacial, use
`unzip -Z1 data/input/grade.zip` para localizar o nome interno e acrescente
`--zip-member 'PASTA/ARQUIVO.gpkg'`.

## Recorte automático por cidade

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/grade.zip \
  --city "Lyon" \
  --country "France" \
  --output data/normalized/lyon.gpkg
```

O geocodificador OSMnx busca o limite municipal por nome; requer internet.
`--country` e `--state` são opcionais e ajudam a evitar ambiguidades.
Também é possível usar `--boundary data/input/lyon.geojson` para recorte
sem geocodificação. Não combine `--city` com `--boundary`.

## Campos com nomes desconhecidos

Se a grade possuir, por exemplo, `ZONE_CODE` e `PESSOAS2021`, informe:

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/grade.gpkg \
  --id-column ZONE_CODE \
  --population-column PESSOAS2021 \
  --output data/normalized/grade.gpkg
```

Se a grade não possuir ID, o programa cria um ID técnico sequencial e
registra isso no relatório. Não cria estimativas populacionais.

## CSV com coordenadas

É possível converter uma tabela CSV quando cada linha contém
latitude, longitude e quantidade de pessoas:

```csv
cell_id,latitude,longitude,population
A,-23.96,-46.33,120
B,-23.97,-46.32,80
```

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/celulas.csv \
  --output data/normalized/celulas.gpkg
```

Para coordenadas em WKT (`POLYGON (...)` ou `POINT (...)`), informe
`--input-crs EPSG:4326` e, se necessário, `--location-column`.
Para nomes incomuns de coordenadas, use `--latitude-column` e
`--longitude-column`. CSV sem localização não pode ser convertido
automaticamente em uma grade espacial.

## Uso na CLI principal

```bash
uv run fifteen-minute-city \
  --city "Lyon" \
  --country "France" \
  --pbf data/input/france-latest.osm.pbf \
  --population-grid data/normalized/lyon.gpkg \
  --population-column POPULACAO \
  --population-id-column ID
```

O algoritmo lê a geometria do GeoPackage independentemente do nome interno
da coluna espacial. O normalizador **não modifica o PostgreSQL, a API ou
os cálculos de acessibilidade**.

## Limitações atuais

Esta implementação suporta grades **vetoriais** e CSV espacial. GeoTIFF
(raster), NetCDF e arquivos tabulares sem localização exigem etapas de leitura
específicas que ainda não foram implementadas. Portanto, o **contrato de saída
é universal**, mas cada formato físico precisa ter um leitor.

Não são feitas desagregação espacial, interpolação, conversão de densidade
para habitantes, nem correção automática de estimativas ou definições
estatísticas incompatíveis.
