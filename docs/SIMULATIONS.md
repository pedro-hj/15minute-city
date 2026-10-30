# Simulações locais e portáveis — FMC1

A PR #21 foi reformulada para **distribuir dados, não executar simulações na VPS**.
O mesmo pacote permite simular em navegadores, Node.js ou futuros clientes nativos
que implementem o formato `FMC1`.

## Arquitetura

1. Uma análise completa roda normalmente e persiste os pesos populacionais por nó.
2. O administrador gera **uma vez** o pacote de determinada execução, unindo
   `graph.graphml` do cache + `node_reachability` e `node.population_weight` do banco.
3. A API distribui `GET /api/v1/executions/{id}/simulation-package` como binário
   compactado em gzip. Não faz Dijkstra nem carrega GraphML durante a requisição.
4. O cliente baixa o arquivo e executa o Dijkstra incremental localmente,
   usando os tempos originais por nó e categoria para manter os indicadores.
5. O arquivo pode ser armazenado localmente no cliente. Chamadas posteriores
   não precisam baixar novamente o pacote.

**A simulação não grava serviços artificiais nem índices hipotéticos no banco.**

## Persistência e migração

A migração `c15fbc26e001` acrescenta `node.population_weight` (nullable).
Nas novas análises com `--enable-db`, o peso de todas as células populacionais
associadas a um nó é somado e armazenado no registro desse nó.

**Análises antigas não podem ser exportadas diretamente**, pois o banco ainda
não possui os pesos populacionais por nó: é necessário executar novamente a
análise após aplicar a migração. Não existem estimativas ou preenchimentos
arbitrários de pesos faltantes.

Antes de usar em produção, faça backup do banco, revise a migração e aplique
com a política normal de deploy do projeto. Esta PR não executa a migração.

## Gerar o pacote na VPS (em ambiente de teste)

Partindo de um clone separado da branch da PR e de uma execução **concluída
e posterior à migração**:

```bash
cd /opt/15minute-city-simulation-test
uv sync --frozen
uv run alembic upgrade head  # somente em banco de teste, após backup
uv run python -m fifteen_minute_city.application.simulation_package \
  --execution-id 12 \
  --cache-dir /opt/15minute-city/data/cache \
  --output-dir data/simulation-packages
```

Use um `DATABASE_URL` de **banco de teste** no ambiente de testes, pois
o comando lê os dados dessa conexão. Gere a execução-base com a branch
atualizada e `--enable-db`, usando uma cópia de testes do PostgreSQL.
O arquivo será `data/simulation-packages/12.fmc.gz`.

O exportador valida `pbf_checksum`, `graph_cache_key`, arquivos de cache,
soma populacional e presença de tempos para cada nó/categoria.
A API não gera pacotes automaticamente: eles precisam ser preparados antes.

## API: somente transferência

```http
GET /api/v1/executions/12/simulation-package
X-API-Key: SUA_CHAVE
```

- Resposta: `application/octet-stream`, com `Content-Encoding: gzip`.
- A maioria dos clientes HTTP **descompacta a resposta automaticamente**.
- Resposta `404` se a execução não estiver concluída ou o pacote não existir.
- Configurar `SIMULATION_PACKAGE_DIR` no serviço da API apontando para a
  pasta onde os arquivos foram gerados.
- A autenticação por `X-API-Key` permanece obrigatória.

**Segurança:** não embuta chaves privilegiadas num frontend público. Para
simulação diretamente em um site público, será necessário habilitar uma
política de acesso público específica ou um mecanismo de autenticação
adequado para clientes não confiáveis.

## Simular com Node.js (sem navegador)

O arquivo GeoJSON usa `FeatureCollection`, `Point`, coordenadas
`[longitude, latitude]`, `properties.category` em `health`, `education`,
`food`, `culture` e `properties.name` opcional:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {"category": "health", "name": "Nova UBS"},
      "geometry": {
        "type": "Point",
        "coordinates": [-46.405, -24.005]
      }
    }
  ]
}
```

Execute com o arquivo local:

```bash
node client/simulate-cli.mjs \
  data/simulation-packages/12.fmc.gz \
  data/input/cenarios/novos-servicos.geojson \
  > resultado.json
```

Ou diretamente pela API:

```bash
API_KEY="SUA_CHAVE" node client/simulate-cli.mjs \
  https://cidade15.com.br/api/v1/executions/12/simulation-package \
  data/input/cenarios/novos-servicos.geojson
```

Substitua o ID e as coordenadas pelas informações reais do ambiente.

## Simular em um aplicativo web

A biblioteca `client/simulation.mjs` usa somente APIs padrão de JavaScript
e não depende de Node.js, DOM nem frameworks. Pode ser importada por qualquer
aplicação ESM no navegador:

```javascript
import {readPackage, simulate} from "./simulation.mjs";

const response = await fetch("/api/v1/executions/12/simulation-package", {
  headers: {"X-API-Key": "CHAVE_FORNECIDA_POR_AUTENTICACAO_SEGURA"}
});
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const data = readPackage(await response.arrayBuffer());

const output = simulate(data, [
  {name: "Nova UBS", category: "health", longitude: -46.405, latitude: -24.005}
]);
console.log(output.delta.population);
```

O navegador descompacta automaticamente o gzip transmitido com o cabeçalho
HTTP correto. Para evitar bloqueio da interface, execute o módulo em
`Web Worker`, e armazene o pacote por versão com IndexedDB/Cache Storage.

## Métricas calculadas

O motor efetua Dijkstra **sem limite de distância**, em arestas invertidas
de um grafo dirigido, a partir dos novos serviços. Para cada nó/categoria,
o novo tempo é o mínimo entre o tempo original e o tempo até os serviços
adicionados. As demais categorias não executam Dijkstra novamente.

Calcula, para população ponderada e para nós sem ponderação:

- percentual de cobertura em até 15 minutos;
- percentual inalcançável;
- tempo médio e mediano entre nós/origens alcançáveis;
- cobertura geral (interseção de todas as categorias da execução);
- diferenças de cobertura em pontos percentuais.

Os pesos populacionais das células com o mesmo nó são agregados; isso
preserva os indicadores ponderados, incluindo a mediana, porque células
associadas ao mesmo nó têm os mesmos tempos.

A associação de pontos ao grafo é feita no cliente por distância
geográfica aproximada, com limite de 250 m. A primeira versão não inclui
a fronteira administrativa exata no pacote; revise os pontos do cenário
para garantir que estão dentro da cidade.

## Formato FMC1

Arquivo descompactado em little-endian:

- 20 bytes de cabeçalho: `FMC1`, comprimento do JSON, nós, arestas,
  categorias (cinco campos, inteiros `uint32` onde aplicável);
- metadados JSON, preenchimento de zeros até alinhamento a 8 bytes;
- coordenadas `(lon, lat)` como `float64[2*N]`;
- população por nó `float64[N]`;
- tempos-base em segundos `float64[N*K]`, com `Infinity` para inalcançáveis;
- offsets CSR `uint32[N+1]`;
- destinos CSR `uint32[M]`;
- pesos de arestas (tempo em segundos) `float64[M`.

As arestas CSR são **invertidas** em relação ao grafo dirigido original.
O pacote é gerado uma vez por execução, comprimido com gzip na VPS,
e o motor cliente lê o conteúdo descompactado.

## Limitações e próximos passos

- A implementação inicial usa JavaScript portátil (browser e Node.js).
  Clientes Python, Rust, Java ou WASM podem ler o mesmo FMC1, mas ainda
  precisariam implementar um leitor e o motor de cálculo.
- Uma simulação no cliente consome sua própria RAM e CPU; é necessário
  medir desempenho em computadores e smartphones reais.
- O custo de transferência inicial não desaparece. Depois de armazenar
  o pacote localmente, somente novas versões precisam ser baixadas.
- A renderização de mapas e a interface para arrastar serviços não fazem
  parte desta PR; ela entrega **o motor portátil e o transporte dos dados**.
- É necessário validar a equivalência do pacote com uma análise real de
  Praia Grande antes de disponibilizar a funcionalidade publicamente.
