# Simulações no servidor — FMC1 e POST /simulate

Esta funcionalidade roda **na VPS**, não no navegador: o cliente envia
estabelecimentos hipotéticos para `POST /api/v1/executions/{id}/simulate`
e recebe os indicadores originais, simulados e as diferenças em JSON.
A API **não grava** estabelecimentos hipotéticos ou novos índices no banco.

## Arquitetura

1. Uma execução real com `--enable-db` salva os tempos de caminhada por nó,
   as categorias e os pesos populacionais agregados em PostgreSQL.
2. O administrador prepara **uma vez por execução** o pacote interno `FMC1`,
   combinando `graph.graphml` do cache com os resultados persistidos.
3. A API valida `X-API-Key`, verifica que a execução está concluída e carrega
   o pacote compacto da pasta `SIMULATION_PACKAGE_DIR`. O pacote descompactado
   permanece num cache LRU de até duas execuções **por processo** e é
   recarregado se o arquivo for substituído (alteração de mtime/tamanho).
4. A API associa cada novo estabelecimento ao nó caminhável mais próximo
   (até 250 m), executa Dijkstra no grafo **reverso** somente para as
   categorias modificadas e considera o menor tempo entre o existente
   e o hipotético.
5. A resposta inclui coberturas, médias, medianas e diferenças em pontos
   percentuais, ponderadas pela população e por nós viários.

O motor `application/server_simulation.py` usa Python, NumPy e `heapq`.
A requisição **não** chama um subprocesso Node.js, não carrega GraphML
nem consulta o banco para cada nó. A verificação da execução concluída
é uma consulta leve ao PostgreSQL.

## Preparação no ambiente de homologação

Requer migração `c15fbc26e001` (`node.population_weight`) e análise
**concluída depois da migração**, pois as análises anteriores não têm
pesos populacionais por nó.

```bash
cd /opt/15minute-city-staging
env -u DATABASE_URL uv run alembic current

# Troque 3 pelo ID de uma execução concluída na homologação.
env -u DATABASE_URL uv run python \
  -m fifteen_minute_city.application.simulation_package \
  --execution-id 3 \
  --cache-dir /opt/15minute-city-staging/data/cache \
  --output-dir /opt/15minute-city-staging/data/simulation-packages
```

O arquivo gerado é `data/simulation-packages/3.fmc.gz`.
No `.env` da homologação:

```dotenv
DATABASE_URL=postgresql+psycopg://tcc_staging:SENHA@127.0.0.1:5432/cidade15_staging?sslmode=disable
API_HOST=127.0.0.1
API_PORT=8001
API_KEYS=CHAVE_EXCLUSIVA_DE_HOMOLOGACAO
SIMULATION_PACKAGE_DIR=/opt/15minute-city-staging/data/simulation-packages
```

Assegure que a conexão aponta ao banco de teste antes de migrar ou
processar dados. Esta PR **não** faz deploy nem migra a produção.

Para iniciar a API localmente:

```bash
env -u DATABASE_URL uv run fifteen-minute-city-api
```

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

O retorno contém:

- `execution_id` e `added_services` (incluindo nó selecionado e
  `snap_distance_m`);
- `baseline.population` / `baseline.nodes`: indicadores originais;
- `simulated.population` / `simulated.nodes`: indicadores atualizados;
- `delta.population` / `delta.nodes`: diferenças de coberturas em **pontos
  percentuais** (`category_coverage` e `overall_coverage`);
- `processing_time_ms`: tempo de cálculo no motor, sem incluir rede,
  leitura inicial do FMC1 nem validação HTTP.

As métricas por categoria são `coverage_percentage`,
`unreachable_percentage`, `mean_travel_time_minutes` e
`median_travel_time_minutes`. A cobertura geral exige alcançar
**todas as categorias analisadas em até 15 minutos**; não é uma média.
O Dijkstra não aplica cutoff de 15 minutos porque as médias e medianas
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

A geração do pacote ainda é **administrativa e manual**. Não há
endpoint público de download `GET /simulation-package`. Os arquivos
FMC1 permanecem internos à VPS. O motor ESM em `client/` pode ser
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
