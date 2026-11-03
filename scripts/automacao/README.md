# Análises automatizadas por país

Executa a CLI `fifteen-minute-city` uma cidade por vez, com seleção de estado ou
região, logs, retomada e coleta científica de desempenho.

Na raiz do repositório, Linux:

```bash
bash scripts/automacao/analisar_brasil.sh
```

Windows/PowerShell, com o projeto e os dados instalados localmente:

```powershell
.\scripts\automacao\analisar_brasil.ps1
```

Para executar na VPS pelo PowerShell:

```powershell
ssh -t USUARIO@SERVIDOR "bash /opt/15minute-city/scripts/automacao/analisar_brasil.sh"
```

Informe o código ou nome exibido no menu. No Brasil, por exemplo: `SP`, `35` ou
`São Paulo`. A opção `0` seleciona o país inteiro. Para consultar primeiro a lista:

```bash
bash scripts/automacao/analisar_brasil.sh --region SP --list-only
```

## Países

| País | Lançador (também disponível como `.ps1`) | Fonte da lista |
| --- | --- | --- |
| Brasil | `analisar_brasil.sh` | IBGE, municípios por UF |
| França | `analisar_franca.sh` | API Géo, comunas por região |
| Espanha | `analisar_espanha.sh` | GeoNames, localidades habitadas |
| Itália | `analisar_italia.sh` | GeoNames, localidades habitadas |
| Austrália | `analisar_australia.sh` | GeoNames, localidades habitadas |
| China | `analisar_china.sh` | GeoNames, localidades habitadas |
| Países Baixos | `analisar_netherlands.sh` | GeoNames, localidades habitadas |
| Bélgica | `analisar_belgica.sh` | GeoNames, localidades habitadas |
| Estados Unidos | `analisar_estados_unidos.sh` | GeoNames, localidades habitadas |

GeoNames não garante uma lista exaustiva de municípios oficiais. A opção
`--cities-csv` permite substituir a fonte por uma lista revisada. O catálogo não
garante que o geocodificador encontre o polígono de cada localidade.

## Configuração e dados

É necessário `uv` no PATH. Os lançadores preparam um ambiente isolado com
`psutil==7.2.2`; a primeira execução pode baixar dependências. A CLI continua
usando o ambiente do projeto e a configuração habitual de banco de dados.

A raiz do projeto é detectada pelo `pyproject.toml`. `--project-dir` permite
usar outra instalação. `arquivos.example.json` contém os caminhos iniciais de
Brasil e França. Os caminhos informados são salvos em `arquivos.json`, ignorado
pelo Git. Também é possível copiar o modelo para esse arquivo e editá-lo.

O PBF e a grade devem cobrir a região escolhida. A grade deve ser um GPKG
normalizado com uma única camada e colunas fixas `POPULATION` e `ID`.

## Resultados científicos

Cada lote grava em `logs/lotes/`:

- `cidades.csv`: lista selecionada.
- `resumo.csv`: resultado e duração de cada tentativa.
- `metricas_cientificas.csv`: duração, CPU, RAM e contexto da máquina por cidade.
- `ambiente.json`: hardware, software, arquivos de entrada e método de coleta.
- `cidade_*.log`: saída completa da CLI.
- `cidade_*.recursos.csv`: série temporal de amostras.
- `cidade_*.metricas.json`: métricas detalhadas e comando executado.

CPU e RSS acompanham a CLI e seus descendentes. Os campos `machine_*` descrevem
a máquina inteira, incluindo outros serviços. A memória é amostrada; picos
entre amostras podem ser perdidos, e a soma de RSS pode contar páginas
compartilhadas mais de uma vez. O tempo corresponde à execução completa da CLI.

Opções úteis:

```bash
# Retomar sem repetir sucessos anteriores com as mesmas entradas.
bash scripts/automacao/analisar_brasil.sh --region SP --resume

# Amostrar a cada meio segundo.
bash scripts/automacao/analisar_brasil.sh --region SP --sample-interval 0.5

# Imprimir três comandos sem executar análises.
bash scripts/automacao/analisar_brasil.sh --region SP --dry-run --limit 3
```

`--hash-inputs` registra SHA256 integral do PBF e da grade antes das medições.
Essa leitura pode aquecer o cache do sistema. A retomada não detecta mudanças
de metodologia, código ou banco: nesses casos, execute sem `--resume`.

## Verificação

Na raiz do repositório, execute a suíte independente sem iniciar análises reais:

```bash
uv run --no-project --with psutil==7.2.2 python -m unittest discover -s scripts/automacao/tests -v
```

Os testes usam catálogos e CLI simulados, além de processos controlados para
verificar CPU, interrupção e ausência de dados. Não precisam de PBFs ou banco.

Consulte [LEIA-ME.txt](LEIA-ME.txt) para os campos, unidades, limitações e
exemplos completos para Linux e PowerShell.
