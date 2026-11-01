# Simulações no servidor — FMC1 e POST /simulate

Esta funcionalidade roda **na VPS**, não no navegador: o cliente envia
estabelecimentos hipotéticos para `POST /api/v1/executions/{id}/simulate`
e recebe os indicadores originais, simulados e as diferenças em JSON.
A API **não grava** estabelecimentos hipotéticos ou novos índices no banco.

## Arquitetura

1. A CLI executa a análise real com `--enable-db`, persistindo os tempos
   de caminhada, as categorias e os pesos populacionais no PostgreSQL.
2. **Após a conclusão e persistência da análise**, a própria CLI executa
   `export_completed_execution()`. A função lê o `graph.graphml` do cache e
   os dados persistidos no PostgreSQL para gerar `<execution_id>.fmc.gz`.
3. A API valida `X-API-Key`, confirma a execução concluída e carrega esse
   pacote interno a partir de `SIMULATION_PACKAGE_DIR`. Os dados descompactados
   permanecem em cache LRU de até duas execuções **por processo**.
4. Para cada novo estabelecimento, a API encontra o nó caminhável mais próximo
   (máximo 250 m). Executa Dijkstra no grafo reverso, **uma vez por categoria
   afetada**, e considera o menor tempo entre os serviços reais e hipotéticos.
5. A resposta apresenta **somente as categorias incluídas no cenário**, cada
   uma com `population` e `nodes`: indicadores `before`, `after` e
   `coverage_delta_percentage_points`.

O motor `application/server_simulation.py` usa Python, NumPy e `heapq`.
O endpoint não executa Node.js, não carrega GraphML por requisição e
não altera os dados originais no PostgreSQL.

## Geração automática do FMC1 na análise

A automação fica em
`src/fifteen_minute_city/main.py`, função `main()`, logo após
`region.calculate_accessibility()` e a gravação do JSON de saída.

Quando `--enable-db` estiver presente, a CLI:

1. Obtém o `region.execution_id` da execução concluída;
2. Lê `SIMULATION_PACKAGE_DIR` do ambiente (padrão:
   `data/simulation-packages`);
3. Abre uma sessão de leitura com `session_scope()`;
4. Chama `export_completed_execution(db, execution_id, cache_dir, output_dir)`;
5. Mostra o caminho de `<execution_id>.fmc.gz` no terminal.

O gerador está implementado em
`src/fifteen_minute_city/application/simulation_package.py`, função
`export_completed_execution()`. Ele **não** precisa reexecutar a análise;
apenas reúne os resultados já persistidos com o grafo do cache.

Exemplo na homologação:

```bash
cd /opt/15minute-city-staging

env -u DATABASE_URL uv run fifteen-minute-city \
  --city "Santos" \
  --state "São Paulo" \
  --country "Brazil" \
  --pbf /opt/15minute-city/data/input/brazil-latest.osm.pbf \
  --population-grid /opt/15minute-city/data/input/grade_idXX.zip \
  --population-column POPULATION_COLUMN \
  --cache-dir /opt/15minute-city-staging/data/cache \
  --enable-db \
  --output-mode simple \
  --verbose
```

Substitua `grade_idXX.zip` e `POPULATION_COLUMN` pelos dados identificados
na grade populacional da cidade. Na saída, você verá:

```text
Result saved at data/output/santos-sao-paulo/...
Preparing FMC1 for completed execution 42...
Simulation package ready at data/simulation-packages/42.fmc.gz
```

Os valores de ID são ilustrativos. Sem `--enable-db`, a análise não gera
pacote FMC1, pois não há execução persistida para exportar.

**Falhas:** se a geração do FMC1 falhar, a CLI encerra com erro informando
que a análise e seu JSON já foram salvos. Ela **não reclassifica**
a execução concluída como falha; o operador pode corrigir o problema
e exportar somente o pacote, sem reprocessar a cidade.

Para preparar pacotes de **análises antigas** (ainda sem FMC1), permanece
disponível o comando manual:

```bash
env -u DATABASE_URL uv run python \
  -m fifteen_minute_city.application.simulation_package \
  --execution-id 42 \
  --cache-dir /opt/15minute-city-staging/data/cache \
  --output-dir /opt/15minute-city-staging/data/simulation-packages
```

Uma análise que antecede a migração `c15fbc26e001` precisa ser refeita,
pois não dispõe dos pesos populacionais por nó.

No `.env` da homologação:

```dotenv
DATABASE_URL=postgresql+psycopg://tcc_staging:SENHA@127.0.0.1:5432/cidade15_staging?sslmode=disable
API_HOST=127.0.0.1
API_PORT=8001
API_KEYS=CHAVE_EXCLUSIVA_DE_HOMOLOGACAO
SIMULATION_PACKAGE_DIR=/opt/15minute-city-staging/data/simulation-packages
```

**Confirme a conexão ao banco de homologação antes de iniciar a CLI.**
Esta PR não executa deploy ou migrações em produção.

## Requisição HTTP

```http
POST /api/v1/executions/3/simulate
X-API-Key: SUA_CHAVE
Content-Type: application/json

{
  "services": [
    {
      "category": "culture",
      "name": "Novo equipamento cultural",
      "latitude": -24.031453,
      "longitude": -46.491341
    }
  ]
}
```

Com `curl`, sem colocar a chave literalmente no histórico:

```bash
read -r -s -p "Chave da API: " API_KEY
echo

curl -fsS -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"services":[{"category":"culture","name":"Novo equipamento cultural","latitude":-24.031453,"longitude":-46.491341}]}' \
  http://127.0.0.1:8001/api/v1/executions/3/simulate \
  | python3 -m json.tool
```

O retorno agora é **restrito às categorias afetadas**:

- `execution_id`: identificador da análise original;
- `added_services`: pontos simulados e distância de associação ao grafo;
- `results.<category>.population`: dados populacionais da categoria;
- `results.<category>.nodes`: dados por nós viários da mesma categoria;
- `before` e `after`: cobertura, inalcançáveis, tempos médio e mediano;
- `coverage_delta_percentage_points`: variação de cobertura em pontos
  percentuais (`after - before`);
- `processing_time_ms`: tempo de cálculo do motor, sem incluir rede nem
  a primeira leitura do FMC1.

Exemplo **ilustrativo** da estrutura simplificada (valores fictícios):

```json
{
  "execution_id": 42,
  "added_services": [
    {
      "category": "culture",
      "name": "Novo equipamento cultural",
      "longitude": -46.491341,
      "latitude": -24.031453,
      "graph_node_index": 123,
      "snap_distance_m": 12.4
    }
  ],
  "results": {
    "culture": {
      "population": {
        "before": {
          "coverage_percentage": 17.11,
          "unreachable_percentage": 5.0,
          "mean_travel_time_minutes": 22.0,
          "median_travel_time_minutes": 18.0
        },
        "after": {
          "coverage_percentage": 19.82,
          "unreachable_percentage": 4.5,
          "mean_travel_time_minutes": 21.0,
          "median_travel_time_minutes": 17.0
        },
        "coverage_delta_percentage_points": 2.71
      },
      "nodes": {
        "before": {
          "coverage_percentage": 16.0,
          "unreachable_percentage": 7.0,
          "mean_travel_time_minutes": 25.0,
          "median_travel_time_minutes": 19.0
        },
        "after": {
          "coverage_percentage": 18.0,
          "unreachable_percentage": 6.0,
          "mean_travel_time_minutes": 24.0,
          "median_travel_time_minutes": 18.0
        },
        "coverage_delta_percentage_points": 2.0
      }
    }
  },
  "processing_time_ms": 35.2
}
```

Se o cenário contiver `culture` e `health`, apenas essas duas categorias
aparecerão em `results`, independentemente da quantidade de pontos
simulados por categoria. O endpoint não retorna indicadores gerais nem
categorias não modificadas. Essas informações continuam disponíveis nos
endpoints de consulta das análises originais.

O Dijkstra continua **sem cutoff de 15 minutos**, pois as médias e medianas
consideram todos os nós alcançáveis.

## Validação e erros

- `401`: chave ausente ou incorreta;
- `404`: execução não concluída ou pacote ainda não preparado;
- `422`: corpo inválido, categoria desconhecida ou ponto a mais de
  250 metros da rede caminhável;
- `503`: chave da API não configurada ou FMC1 ilegível/inválido.

São aceitos de 1 a 200 novos serviços por requisição. Pontos são
interpretados em WGS84 (latitude/longitude em graus decimais).
A primeira versão não armazena o limite administrativo no pacote,
portanto a proximidade do nó não substitui uma validação rigorosa do
ponto dentro do município.

A geração é automática após novas análises com `--enable-db`;
o exportador manual continua disponível para reparar ou preparar uma análise
já concluída. Não há endpoint público de download `GET /simulation-package`.
Os arquivos FMC1 permanecem internos à VPS. O motor ESM em `client/` pode ser
mantido como referência independente para testes de equivalência,
mas não é necessário para consumir a API.

## Desempenho e operação

O formato binário evita abrir GraphML e consultar milhões de registros
a cada `POST`. Entretanto, o primeiro carregamento do pacote ainda
consome tempo e memória; Gunicorn com múltiplos workers manterá seu
**próprio cache** por processo, podendo multiplicar a RAM utilizada.

O limite de tamanho descompactado é de 1 GiB por pacote e há até dois
pacotes em cache por processo. Para cidades grandes, avalie o orçamento
de memória e a política de workers antes de aumentar esses limites.
NumPy acelera cálculos agregados, mas a implementação de Dijkstra em
Python deve ser medida sob concorrência e comparada com o motor JS.

Antes de produção, faça testes com dados reais, compare as métricas-base
com a API de análises e meça latência p50/p95, primeiro carregamento
e concorrência. Não extrapole os 168 ms medidos num pacote fictício
para um cenário real com múltiplos usuários.
