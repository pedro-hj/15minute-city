# Manual da API - 15minute-city

## 1. Catálogo completo de endpoints

As rotas de consulta utilizam `GET`; simulações utilizam `POST`. Os parâmetros entre chaves são substituídos por valores reais.

| Método e caminho | Finalidade |
| --- | --- |
| `GET /health` | Verifica se o processo HTTP está respondendo (sem chave). |
| `GET /api/v1/version` | Informa nome e versão da API. |
| `GET /api/v1/cities` | Lista municípios cadastrados. |
| `GET /api/v1/cities/{city_id}` | Obtém um município específico. |
| `GET /api/v1/categories` | Lista as categorias registradas. |
| `GET /api/v1/cities/{city_id}/executions` | Lista execuções concluídas do município. |
| `GET /api/v1/executions/{execution_id}` | Retorna um resultado detalhado por execução concluída. |
| `POST /api/v1/executions/{execution_id}/simulate` | Adiciona serviços hipotéticos e retorna os indicadores recalculados pela VPS, sem modificar a análise original. |
| `GET /api/v1/cities/{city_id}/latest` | Retorna o resultado detalhado da execução concluída mais recente. |
| `GET /api/v1/cities/{city_id}/latest/{strategy}` | Retorna o relatório completo de uma estratégia. |
| `GET /api/v1/cities/{city_id}/latest/{strategy}/{metric}` | Consulta uma métrica geral da última execução. |
| `GET /api/v1/cities/{city_id}/latest/{strategy}/{category}/{metric}` | Consulta uma métrica de categoria da última execução. |
| `GET /api/v1/cities/{city_id}/history` | Retorna os relatórios detalhados ao longo das execuções concluídas. |
| `GET /api/v1/cities/{city_id}/history/{strategy}/{metric}` | Histórico de uma métrica geral. |
| `GET /api/v1/cities/{city_id}/history/{strategy}/{category}/{metric}` | Histórico de uma métrica de categoria. |

### 1.1. Parâmetros dos caminhos

| Parâmetro | Significado | Exemplos |
| --- | --- | --- |
| `city_id` | Identificador numérico do município. | `1`, `4` |
| `execution_id` | Identificador numérico de uma execução concluída. | `12` |
| `strategy` | Estratégia pública de origem. | `population`, `nodes` |
| `category` | Código de categoria registrado no banco. | `health`, `education`, `food`, `culture` |
| `metric` | Nome da métrica disponibilizada no contexto solicitado. | `coverage_percentage` |

Os endpoints de lista e histórico recebem parâmetros de consulta opcionais: `limit` (padrão `100`, mínimo `1`, máximo `500`) e `offset` (padrão `0`, mínimo `0`). A ordenação é decrescente por data de processamento, com ID como critério de desempate. O campo `count` em históricos informa o número de itens **retornados na página**, e não o total de registros existentes no banco.

## 2. Estratégias e interpretação dos indicadores

A estratégia `population` corresponde à persistência `population_grid`: cada origem representa uma unidade espacial com peso populacional. É a referência indicada para responder **qual percentual da população** tem acesso aos serviços em até 15 minutos.

A estratégia `nodes` corresponde à persistência `network_nodes`: cada nó do grafo caminhável tem peso equivalente. Ela serve principalmente à comparação metodológica e **não** deve ser interpretada como percentual populacional.

Para cada categoria, `coverage_percentage` é o percentual do peso de origens que consegue alcançar ao menos um serviço daquela categoria dentro do limiar. `overall_coverage_percentage` exige que as origens atendam **simultaneamente a todas as categorias analisadas**. Portanto, o índice geral não é a média simples dos índices por categoria.

Os tempos médio e mediano são calculados entre origens que possuem caminho até algum estabelecimento da categoria. Consequentemente, **uma média de 59 minutos não significa que 59% das origens estejam cobertas**, nem que 17% tenham média de 15 minutos: a cobertura é expressa por `coverage_percentage`.

### 2.1. Métricas de categoria

| Métrica | Significado | Unidade |
| --- | --- | --- |
| `total_weight` | Soma dos pesos das origens consideradas. | `population` ou `node_count` |
| `reachable_weight` | Peso com caminho até um serviço, sem exigir 15 minutos. | Peso da estratégia |
| `within_threshold_weight` | Peso com caminho até serviço em até o limiar. | Peso da estratégia |
| `unreachable_weight` | Peso sem caminho até o serviço. | Peso da estratégia |
| `coverage_percentage` | Percentual de peso em até o limiar. | `%` |
| `unreachable_percentage` | Percentual sem caminho até serviço. | `%` |
| `mean_travel_time_minutes` | Tempo médio ponderado entre origens alcançáveis. | minutos |
| `median_travel_time_minutes` | Tempo mediano ponderado entre origens alcançáveis. | minutos |

### 2.2. Métricas gerais

| Métrica | Significado |
| --- | --- |
| `total_weight` | Peso total de origens analisadas. |
| `overall_coverage_percentage` | Percentual de origens com acesso às quatro categorias analisadas em até o limiar. |
| `overall_unreachable_percentage` | Percentual de origens que não consegue alcançar alguma das categorias por caminho de rede, sem relação direta com o limiar. |

A API devolve porcentagens como números de `0` a `100` (por exemplo, `17.11`, não `0.1711`). O campo `unit` das respostas individuais informa `percent`, `minutes` ou a unidade de peso da estratégia.

## 3. Exemplos de consultas e respostas

### 3.1. Municípios cadastrados

```http
GET /api/v1/cities
X-API-Key: SUA_CHAVE
```

Exemplo **ilustrativo** de resposta HTTP `200`:

```json
[{"id":1,"name":"Praia Grande","country":"Brazil"}]
```

### 3.2. Métrica específica: cobertura de saúde

```http
GET /api/v1/cities/1/latest/population/health/coverage_percentage
X-API-Key: SUA_CHAVE
```

Resposta **ilustrativa**:

```json
{
  "city_id": 1,
  "execution_id": 12,
  "processed_at": "2026-10-08T12:00:00+00:00",
  "strategy": "population",
  "category": "health",
  "metric": "coverage_percentage",
  "value": 82.5,
  "unit": "percent",
  "threshold_minutes": 15.0
}
```

Nesse exemplo, `82.5` representa 82,5% da população ponderada com acesso à categoria saúde em até 15 minutos. Os valores acima não representam medição real de Praia Grande.

### 3.3. Índice geral e comparação

```http
GET /api/v1/cities/1/latest/population/overall_coverage_percentage
GET /api/v1/cities/1/latest
```

A primeira rota retorna apenas uma métrica no formato exemplificado acima. A segunda retorna `execution`, `node_report`, `population_report` e `comparison`. Os relatórios de estratégia podem ser `null` se não foram persistidos na execução. A comparação também será `null` quando alguma estratégia estiver indisponível.

Quando presente, a comparação segue `population_report - node_report` e usa **pontos percentuais**. Um delta de `+8.0` significa que a cobertura ponderada pela população foi oito pontos percentuais maior do que a cobertura ponderada por nós, não 8% de aumento relativo.

### 3.4. Histórico da cobertura da categoria cultura

```http
GET /api/v1/cities/1/history/population/culture/coverage_percentage?limit=20&offset=0
```

A resposta contém dados de identificação do município, estratégia, categoria, métrica, `count` e um vetor `results`, com cada observação associada a um `execution_id` e `processed_at`. Um histórico vazio retorna `results: []` e `count: 0` se o município existir.

**Simulações no servidor:**

```http
POST /api/v1/executions/12/simulate
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

A resposta apresenta `execution_id`, `added_services`,
`results` e `processing_time_ms`. Apenas as categorias afetadas
são incluídas em `results`; cada categoria contém as abordagens
`population` e `nodes`, com `before`, `after` e
`coverage_delta_percentage_points` (diferença em pontos percentuais).

Por exemplo, uma simulação somente de cultura apresenta o formato:

```json
{
  "execution_id": 12,
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

**Valores meramente ilustrativos.** A rota não retorna categorias não
afetadas nem a cobertura geral; esses dados podem ser consultados nos
endpoints de análise. São aceitos de 1 a 200 estabelecimentos por requisição,
nas categorias que compõem a execução (`health`, `education`, `food`,
`culture`, quando analisadas). As coordenadas são campos separados em
latitude e longitude, em graus decimais, com associação à rede caminhável
em até 250 m.

Após uma nova análise concluída com `--enable-db`, a CLI gera o pacote
FMC1 **automaticamente** a partir dos dados do PostgreSQL e do GraphML
em cache. O serviço FastAPI mantém até dois pacotes em memória por
processo, sem alterar o PostgreSQL durante simulações. Não existe rota
pública para baixar FMC1. A exportação manual permanece disponível
para análises já concluídas. Consulte `docs/SIMULATIONS.md` para o
fluxo completo e o comando de recuperação.

## 4. Códigos de resposta e erros comuns

| HTTP | Situação | Ação recomendada |
| --- | --- | --- |
| `200` | Consulta bem-sucedida. | Ler o JSON; listas vazias são possíveis. |
| `401` | Chave ausente ou inválida em `/api/v1/`. | Conferir `X-API-Key` sem divulgar a chave. |
| `404` | Município, execução, categoria, estratégia, métrica ou pacote de simulação indisponível. | Consultar IDs, códigos e execuções concluídas; preparar o pacote FMC1, se necessário. |
| `422` | Parâmetro inválido, como `limit=0` ou ID não numérico. | Corrigir tipos e limites informados. |
| `503` | Autenticação não configurada ou pacote de simulação corrompido/indisponível. | Conferir `API_KEYS` e integridade do FMC1. |
| `500` | Falha inesperada, incluindo possíveis problemas de banco. | Consultar logs do serviço e saúde do banco. |

**Atenção:** a rota `/health` confirma que o servidor HTTP responde, mas **não verifica a conectividade com o banco de dados**. Uma consulta às cidades autenticada é um teste mais abrangente.
