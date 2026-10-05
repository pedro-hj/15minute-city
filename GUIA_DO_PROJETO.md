# Guia do projeto

## Camadas

- `main.py`: recebe argumentos, coordena a execução e grava o JSON.
- `config.py`: normaliza e valida os parâmetros da análise.
- `core/modules/locales.py`: fachada `Region`, que organiza o fluxo municipal.
- `infrastructure/osm/graph.py`: recorta o PBF, constrói e armazena o grafo.
- `infrastructure/osm/services.py`: extrai, categoriza e localiza serviços.
- `infrastructure/origins.py`: transforma a grade populacional em origens.
- `domain/models.py`: representa entradas, resultados e comparações.
- `domain/reachability.py`: executa o cálculo puro de acessibilidade.
- `application/analysis_runner.py`: executa e compara as duas estratégias.

## Sequência de execução

1. `main()` interpreta a CLI e cria `Region`.
2. `Region.build_graph()` resolve o limite e carrega ou constrói o grafo.
3. `Region.locate_services()` extrai os serviços do PBF municipal.
4. `Region.load_population_grid()` recorta a grade e cria `OriginSet`.
5. `Region.calculate_accessibility()` chama o executor da aplicação.
6. O executor calcula os relatórios populacional e por nós.
7. `AnalysisOutcome.to_dict()` prepara a saída.
8. `write_result()` grava um JSON por município e execução.

## Regra arquitetural principal

As camadas externas leem arquivos e chamam programas; o domínio recebe objetos
em memória e calcula resultados sem conhecer PBF, GeoJSON, banco ou terminal.
Isso permite testar a regra científica com grafos e populações artificiais.

## Como depurar

- Falha no recorte ou Osmium: consulte `infrastructure/osm`.
- Serviço ausente ou mal classificado: consulte `constants.py` e `services.py`.
- Grade ou população incorreta: consulte `infrastructure/origins.py`.
- Percentuais incorretos: consulte `domain/reachability.py`.
- Argumento ou arquivo de saída: consulte `main.py`.

## Comandos úteis

```bash
uv run fifteen-minute-city --help
uv run pytest
uv run pytest tests/unit/test_reachability.py -v
uv run ruff check src tests
uv run ruff format --check src tests
```
