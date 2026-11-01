# Normalizador universal de grades populacionais

O fluxo é: **arquivo de origem + mapeamento dos campos → arquivo padronizado**.
O código não depende de Brasil, França, instituto estatístico ou perfil.
Você informa quais campos representam o identificador, a localização e a
quantidade de habitantes. O normalizador não adivinha colunas nem cria IDs.

## Comando básico

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/grade.gpkg \
  --id-column CODIGO_CELULA \
  --location-column geometry \
  --population-column HABITANTES \
  --output data/normalized/grade.gpkg
```

Substitua `CODIGO_CELULA` e `HABITANTES` pelos nomes exatos das colunas da origem.

| Parâmetro | O que informar |
| --- | --- |
| `--input` | arquivo GPKG, SHP, GeoJSON, CSV ou ZIP contendo um desses formatos |
| `--id-column` | coluna com o ID único de cada célula; obrigatório |
| `--location-column` | geometria nativa do arquivo vetorial ou coluna WKT do CSV |
| `--population-column` | coluna com a quantidade de habitantes por célula; obrigatório |
| `--output` | caminho do arquivo `.gpkg` normalizado |

Em arquivos vetoriais, `geometry` significa a geometria espacial nativa e pode
ser omitido. Também é aceito o nome físico dessa coluna, como `geom` em um GPKG.
Shapefile armazena a geometria no arquivo `.shp`; ela não é uma coluna comum
da tabela `.dbf`. Localização significa **ponto ou polígono**, não nome de cidade,
endereço ou código municipal.

Se um campo informado não existir, o programa interrompe e mostra as colunas
disponíveis. Se o ZIP contiver várias fontes, indique
`--zip-member 'PASTA/ARQUIVO.gpkg'`. Para arquivos com várias camadas, indique
`--layer NOME_DA_CAMADA`; nenhuma delas é escolhida silenciosamente.

## Exemplos de mapeamento: Brasil e França

Estes exemplos pressupõem os nomes de campos indicados; confira os nomes
existentes na sua edição dos dados. Não há tratamento especial para esses países.

```bash
# Exemplo IBGE: ID_UNICO, geometria do Shapefile e TOTAL.
uv run fifteen-minute-city-normalize-population \
  --input data/input/brasil/grade.zip \
  --id-column ID_UNICO \
  --location-column geometry \
  --population-column TOTAL \
  --output data/normalized/brasil.gpkg

# Exemplo INSEE: idcar_200m, geometria do GeoPackage e ind.
uv run fifteen-minute-city-normalize-population \
  --input data/input/franca/grade.gpkg \
  --id-column idcar_200m \
  --location-column geometry \
  --population-column ind \
  --output data/normalized/franca.gpkg
```

## Arquivo produzido

A camada `grade_populacional` do GeoPackage contém:

| Campo | Conteúdo |
| --- | --- |
| `ID` | identificador original, preservado como texto |
| `LOCALIZACAO` | ponto ou polígono original, convertido para EPSG:4326 |
| `POPULACAO` | quantidade de habitantes, numérica e não negativa |

O GeoPackage tem ainda uma chave técnica `fid`. Ao abrir o arquivo com
GeoPandas, a coluna espacial aparece como `geometry`; seu nome físico continua
sendo `LOCALIZACAO`. Um arquivo `.metadata.json` separado registra a origem,
o mapeamento aplicado, os sistemas de coordenadas e os totais.

IDs nulos, vazios ou repetidos, população ausente, negativa ou não finita,
geometrias vazias, inválidas ou de tipos diferentes de ponto/polígono são
rejeitados. Células com população zero são preservadas na saída. Não há
arredondamento para inteiros, alteração da resolução ou estimativa de habitantes.

## Uso na CLI principal

Após normalizar, o mapeamento é sempre o mesmo, independentemente da origem:

```bash
uv run fifteen-minute-city \
  --city "Lyon" \
  --country "France" \
  --pbf data/input/france-latest.osm.pbf \
  --population-grid data/normalized/franca.gpkg \
  --population-column POPULACAO \
  --population-id-column ID
```

A CLI principal lê a geometria do arquivo, recorta pelo município e associa as
células aos nós da rede. O normalizador preserva os polígonos para essa etapa.

## CSV com localização

Para uma coluna WKT (`POINT (...)` ou `POLYGON (...)`), indique também o sistema
de coordenadas usado na origem:

```bash
uv run fifteen-minute-city-normalize-population \
  --input data/input/celulas.csv \
  --id-column codigo \
  --location-column forma \
  --input-crs EPSG:4326 \
  --population-column moradores \
  --output data/normalized/celulas.gpkg
```

Se a localização estiver em duas colunas, substitua `--location-column` e
`--input-crs` por `--latitude-column LAT --longitude-column LON`.
Essas coordenadas devem estar em graus, no sistema EPSG:4326. CSV deve usar
vírgula como separador. IDs textuais, incluindo zeros à esquerda, são preservados.

## Opções adicionais

- `--city "Lyon" --country "France"`: recorte opcional pelo limite municipal
  obtido com OSMnx; requer internet. `--state` pode ajudar a identificar a cidade.
- `--boundary limite.geojson`: recorte por um arquivo local, em lugar de `--city`.
- `--input-crs EPSG:XXXX`: também permite declarar o sistema de um arquivo
  vetorial sem CRS; não substitui um CRS conhecido por outro incompatível.
- `--overwrite`: permite substituir uma saída existente.

No recorte, o ponto representativo da célula deve estar dentro do limite.
Não se divide a população de células que cruzam a fronteira municipal.

A universalidade está no mapeamento e no contrato de saída. Os leitores atuais
aceitam os formatos acima; GeoTIFF, NetCDF e tabelas sem localização não são
suportados. A coluna populacional deve conter **habitantes por célula**, não
densidade ou porcentagem. Padronizar a estrutura não torna equivalentes as
definições estatísticas de fontes diferentes.
