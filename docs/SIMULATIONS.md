# Simulação de serviços essenciais — CLI

Esta funcionalidade está em revisão na branch `feature/simulate-essential-services`.
Não está disponível na `main` até aprovação e merge.

## 1. Objetivo

Comparar duas análises da **mesma cidade, mesma rede caminhável e mesma
população**:

- **Original:** estabelecimentos existentes no OSM;
- **Simulado:** estabelecimentos existentes + serviços hipotéticos.

Os resultados hipotéticos são calculados apenas em memória e exportados
para JSON. A opção `--simulate-services` é **incompatível** com `--enable-db`
para evitar misturar resultados simulados com os indicadores oficiais.

## 2. Entrada GeoJSON

Um arquivo GeoJSON WGS84 (`EPSG:4326`) com `FeatureCollection` e entre
1 e 200 características do tipo `Point`. A geometria de cada ponto usa
a ordem **[longitude, latitude]**. Cada característica exige
`properties.category` entre `health`, `education`, `food`, `culture`;
`properties.name` é opcional.

Exemplo `data/input/cenarios/novos-servicos.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {"name": "UBS proposta", "category": "health"},
      "geometry": {"type": "Point", "coordinates": [-46.405, -24.005]}
    },
    {
      "type": "Feature",
      "properties": {"name": "Biblioteca proposta", "category": "culture"},
      "geometry": {"type": "Point", "coordinates": [-46.420, -24.010]}
    }
  ]
}
```

**Atenção:** as coordenadas são ilustrativas e devem ser substituídas por
pontos reais de interesse dentro do limite do município e próximos de uma
via caminhável existente no PBF utilizado. O programa rejeita pontos
externos ao município, coordenadas inválidas e pontos a mais de 250 m do
nó mais próximo da rede caminhável (ou do limite personalizado).

Um serviço hipotético não é inserido no arquivo OSM. A categoria declarada
define a métrica afetada. Se `--services` restringir as categorias da análise,
os pontos do cenário devem pertencer às categorias selecionadas.

## 3. Exemplo de execução

```bash
cd /opt/15minute-city-scenario-test

uv run fifteen-minute-city \
  --city "Praia Grande" \
  --state "São Paulo" \
  --country "Brazil" \
  --pbf /opt/15minute-city/data/input/brazil-latest.osm.pbf \
  --population-grid /opt/15minute-city/data/input/grade_id25.zip \
  --population-column TOTAL \
  --population-id-column ID_UNICO \
  --simulate-services data/input/cenarios/novos-servicos.geojson \
  --max-snap-distance-m 250 \
  --output-mode simple \
  --output data/output/cenario-praia-grande.json \
  --overwrite \
  --verbose
```

`--output-mode detailed` é suportado e inclui os relatórios completos
da execução original e da simulação.

Se `--output` não for fornecido, o padrão de simulações é
`data/output/scenarios/<municipio>/<timestamp>.json`, separado das
saídas de análises normais.

## 4. Estrutura do resultado

```json
{
  "mode": "hypothetical_services",
  "location": {"city": "Praia Grande", "state": "São Paulo", "country": "Brazil"},
  "scenario_file": "data/input/cenarios/novos-servicos.geojson",
  "added_services": [
    {"name": "UBS proposta", "category": "health", "coordinates": [-46.405, -24.005], "graph_node_id": 1234}
  ],
  "data_sources": {"pbf_checksum": "<SHA-256>", "population_source": "<grade>"},
  "baseline": {"location": {}, "category_results": {}, "overall_result": 0},
  "simulated": {"location": {}, "category_results": {}, "overall_result": 0},
  "delta": {
    "unit": "percentage_points",
    "population": {"category_coverage": {}, "overall_coverage": 0},
    "nodes": {"category_coverage": {}, "overall_coverage": 0}
  }
}
```

O JSON acima representa **somente o esquema ilustrativo**; IDs e
percentuais não são resultados medidos. Os campos `baseline` e `simulated`
contêm a cobertura real da análise correspondente. `delta` é sempre
**simulado menos original**, em **pontos percentuais**, separado entre
população e nós. O índice geral depende de acesso a **todas as categorias
analisadas simultaneamente**, portanto seu aumento pode ser menor do
que o aumento da categoria que recebeu o novo serviço.

## 5. Como testar na VPS sem alterar a produção

A branch deve ser clonada em **outro diretório**, sem fazer checkout dela
em `/opt/15minute-city`. Como o cálculo não usa banco, não necessita
alterar `DATABASE_URL`, executar migrações ou reiniciar serviços.

```bash
sudo mkdir -p /opt/15minute-city-scenario-test
sudo chown tcc:tcc /opt/15minute-city-scenario-test

sudo -u tcc git clone \
  --branch feature/simulate-essential-services \
  --single-branch \
  https://github.com/pedro-hj/15minute-city.git \
  /opt/15minute-city-scenario-test

cd /opt/15minute-city-scenario-test
sudo -u tcc uv sync --frozen
sudo -u tcc uv run pytest -q tests/unit/test_service_scenarios.py
```

Crie o GeoJSON em `data/input/cenarios/`, propriedade do usuário
`tcc`, com coordenadas verificadas antes de executar o exemplo acima.

O PBF nacional e as grades podem ser usados diretamente a partir do
diretório já existente, **sem copiá-los**. O cache gerado será o da
pasta de testes por padrão, sem tocar no cache da produção. O arquivo
PBF pode ser grande; execute o teste com memória/disco livre e evite
concorrer com outras análises pesadas.

## 6. Limitações e cuidados

- A simulação **adiciona** estabelecimentos; não remove nem altera
  os serviços existentes.
- Vários serviços podem ser acrescentados no mesmo GeoJSON, inclusive
  de categorias diferentes.
- Não altera rede viária, densidade populacional nem considera
  capacidade de atendimento, qualidade ou custo operacional.
- Um ponto inserido representa acesso potencial pela rede, não
  disponibilidade real de vaga ou serviço.
- Não garante que um ponto fictício não coincida com um serviço
  já mapeado; o usuário deve conferir o cenário proposto.
- Ao comparar resultados em diferentes dias, manter constantes PBF,
  população, velocidade e limiar de acessibilidade.
