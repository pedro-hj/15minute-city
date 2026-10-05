# 15minute-city

Aplicação Python para medir a acessibilidade a serviços essenciais pela rede
caminhável, comparando uma análise ponderada pela população com a abordagem
tradicional que atribui o mesmo peso a todos os nós do grafo.

## Requisitos

- Python 3.12 ou superior;
- [uv](https://docs.astral.sh/uv/);
- `osmium-tool` disponível no terminal;
- um arquivo OpenStreetMap no formato `.osm.pbf`;
- uma grade populacional geográfica, incluindo ZIPs de shapefile do IBGE.

## Instalação

```bash
git clone https://github.com/pedro-hj/15minute-city.git
cd 15minute-city
uv sync
```

## Execução

```bash
uv run fifteen-minute-city \
  --city "Praia Grande" \
  --state "São Paulo" \
  --pbf data/input/brazil.osm.pbf \
  --population-grid data/input/grade_id25.zip \
  --population-column TOTAL \
  --population-id-column ID_UNICO
```

O limite municipal é obtido por geocodificação. Para evitar essa consulta,
forneça um arquivo geográfico local:

```bash
--boundary data/input/praia-grande.geojson
```

As categorias podem ser restringidas com:

```bash
--services health education food culture
```

Use `uv run fifteen-minute-city --help` para consultar todas as opções.

### Formato da saída

O modo padrão é o `simple`. Ele mostra somente a localização solicitada e os
resultados ponderados pela população:

```json
{
  "location": {
    "city": "Praia Grande",
    "state": "São Paulo",
    "country": "Brazil"
  },
  "category_results": {
    "health": 82.5,
    "education": 71.0,
    "food": 88.25,
    "culture": 54.75
  },
  "overall_result": 49.5
}
```

Cada resultado é uma porcentagem de `0` a `100`: nas categorias, representa a
parcela da população que alcança aquele tipo de serviço dentro do limite de
tempo; no resultado geral, representa a parcela que alcança todas as categorias.

Para obter os indicadores completos e a comparação com a análise que atribui o
mesmo peso a cada nó do grafo, acrescente:

```bash
--output-mode detailed
```

Dentro de `comparison`, todas as diferenças seguem a operação indicada no próprio
JSON: `population_report - node_report`. Um valor positivo significa que o
indicador ponderado pela população foi maior; um valor negativo significa que o
indicador por nós foi maior. A unidade é ponto percentual.

## Fluxo da análise

```text
PBF + limite municipal
        ↓
grafo caminhável com tempos de percurso
        ↓
serviços agrupados em health, education, food e culture
        ↓
grade populacional recortada e associada aos nós
        ↓
Dijkstra com múltiplas fontes por categoria
        ↓
cobertura populacional em até 15 minutos
        ↓
comparação com a abordagem não ponderada por nós
        ↓
JSON separado por município e execução
```

## Saída

Por padrão, cada execução gera um arquivo em:

```text
data/output/<municipio-estado>/<data-e-hora>.json
```

No modo `simple`, o JSON contém somente os resultados ponderados pela população.
No modo `detailed`, contém também o relatório por nós e as diferenças em pontos
percentuais entre as duas estratégias.

## Testes

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```
