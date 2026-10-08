# Análises municipais públicas - implantação pendente de revisão

Esta funcionalidade ainda deve ser aprovada e preparada antes de qualquer merge para `main`.

## Contrato HTTP

- `POST /api/v1/analyses` com `{"ibge_code":"3541000"}`: admite um trabalho público.
- `GET /api/v1/analyses/{request_id}`: informa o estado de um trabalho.
- As duas rotas são públicas, mas as rotas existentes `GET /api/v1/cities/...` continuam exigindo `X-API-Key`.
- `202`: criou trabalho ou retornou trabalho ativo da mesma cidade; `200`: resultado já existente.
- `429` com `Retry-After`: IP já iniciou outra tarefa nos últimos 3600 segundos.
- `503` com `Retry-After`: limite de 10 tarefas ativas atingido.
- `422`: código IBGE inválido; `503`: IBGE indisponível ou servidor não configurado.
- Consulta ao andamento aceita somente o UUID aleatório da tarefa.
- Endereços de usuários ficam no banco somente como HMAC-SHA256; não são armazenados em claro.

## Entrada nacional e seleção de grades

O worker exige, em `/opt/15minute-city/data/input`:

- `brazil-latest.osm.pbf` (arquivo nacional que você já possui);
- todos os `grade_id*.zip` (arquivos nacionais do IBGE que você já possui).

A seleção não infere nenhum estado a partir de `grade_idXX`. A primeira
utilização indexa o bounding box real de cada shapefile ZIP via `pyogrio`
e grava o catálogo em `data/cache/population-grids.json`. Mudanças de tamanho
ou data de modificação invalidam esse catálogo.

Para cada código IBGE, a malha municipal oficial é baixada da API do IBGE e
armazenada em `data/cache/boundaries/`. Todos os ZIPs candidatos são filtrados
espacialmente, e a mescla elimina sobreposições por `ID_UNICO`.

**Verificar antes de ativar:** que cada ZIP possui as colunas `TOTAL` e
`ID_UNICO`, geometria de células e CRS definido; testar municípios no
interior de uma grade e cruzando limites. Confirmar que a malha oficial tem
resolução adequada ao nível de precisão pretendido pelo TCC.

## Migração obrigatória, antes do merge

O deploy atual atualiza o código mas **não executa Alembic**. O modelo City
passará a consultar `ibge_code` e `state` e haverá uma nova tabela de
`analysis_request`. Se o código novo entrar em produção antes da migração,
a API poderá retornar erro 500 até que ela seja aplicada.

Procedimento proposto pelo administrador do banco:

1. Verificar e fazer backup/snapshot do PostgreSQL Aiven.
2. Conferir o conteúdo de `alembic/versions/a1b2c3d4e5f6_public_analysis_requests.py`.
3. Executar `uv run alembic upgrade head` com **credencial administrativa**, fora da API.
4. Conferir a tabela `analysis_request`, índices e colunas `city.ibge_code`, `city.state`.
5. Confirmar explicitamente que a alteração de unicidade de `city` atende aos dados existentes.

A coluna `ibge_code` admite `NULL` nas cidades legadas. As novas cidades
processadas sob demanda recebem o código IBGE de sete dígitos.

## Credenciais mínimas

A API pública existente continua usando `DATABASE_URL` read-only.
A nova admissão pública exige conexão **separada** `ANALYSES_DATABASE_URL`.
Exemplo conceitual de grants (ajuste o nome da role e do banco):

```sql
CREATE ROLE analysis_submitter LOGIN PASSWORD 'SUBSTITUIR';
GRANT CONNECT ON DATABASE defaultdb TO analysis_submitter;
GRANT USAGE ON SCHEMA public TO analysis_submitter;
GRANT SELECT ON public.city, public.execution TO analysis_submitter;
GRANT SELECT, INSERT ON public.analysis_request TO analysis_submitter;
```

O worker deve executar com **outra credencial**, que também permita
`UPDATE` na tabela `analysis_request` e os privilégios de persistência da
análise; não use a role pública de submissão como worker.

**Não colocar segredos em repositórios**. Gerar segredos com
`openssl rand -hex 32`. O arquivo `/etc/15minute-city/api.env` deve ter
`ANALYSES_DATABASE_URL` e `ANALYSES_IP_HMAC_SECRET` além do acesso de
leitura existente:

```ini
ANALYSES_RATE_LIMIT_SECONDS=3600
ANALYSES_QUEUE_MAX=10
API_TRUSTED_PROXY_IPS=127.0.0.1
```

O worker usa `/etc/15minute-city/worker.env` com `DATABASE_URL` de
processamento, `ANALYSES_DATABASE_URL` de fila e:

```ini
ANALYSES_INPUT_DIR=/opt/15minute-city/data/input
ANALYSES_CACHE_DIR=/opt/15minute-city/data/cache
```

O diretório `data/cache` e `data/output` precisam de permissões de escrita
para o usuário `tcc`. A role de submissão não precisa ter permissão de
escrita nos dados de resultado.

## Unidade worker systemd

O arquivo `deploy/fifteen-minute-city-worker.service` é um modelo de
implantação, **não instalado automaticamente**. Após migration,
configuração e deploy autorizados pelo usuário, copiar para
`/etc/systemd/system/`, validar com `systemd-analyze verify`,
habilitar/arrancar com `systemctl enable --now` e acompanhar os logs via
`journalctl -u fifteen-minute-city-worker -f`.

Inicialmente operar **apenas uma instância** do worker. A unidade emprega
`flock` para impedir duas instâncias na mesma VPS. O worker reencaminha
tarefas interrompidas ao reiniciar. Nunca executar duas instâncias em
servidores diferentes sem implementar lease global no PostgreSQL.

## Segurança antes de tornar público

- Manter porta Uvicorn em `127.0.0.1:8000`, nunca expô-la diretamente.
- Configurar HTTPS antes de expor a chave de consulta ou o POST público.
- Encaminhar X-Forwarded-For do Nginx, mas aceitar cabeçalhos de proxy apenas
  de `127.0.0.1` no Uvicorn (`API_TRUSTED_PROXY_IPS`).
- No Nginx, adicionar limite bruto de requisições de POST por IP (por exemplo,
  5/minuto) **além** da regra de 1 tarefa aceita/hora: isso protege o
  endpoint contra spam de códigos IBGE inválidos.
- Observar espaço em disco para a extração temporária de PBF e cache.
- Conferir que o usuário `tcc` só grava nas pastas autorizadas e não tem
  acesso a segredos da aplicação web por outro usuário.
- Avaliar CAPTCHA e limites por conta quando o serviço ganhar tráfego.
- O serviço de localidades do IBGE depende da Internet; erros do serviço
  não devem enfileirar códigos inválidos.

## Testes de aceitação antes de ativar

1. Rodar testes unitários e `alembic upgrade head --sql` no CI.
2. Em homologação, usar credenciais e base de dados separadas para o
   processamento (não consumir a base de produção para testes).
3. Criar trabalho para município sem análise: `202` e estado `queued`.
4. Repetir a mesma cidade: mesmo `request_id`, não cria tarefa adicional.
5. Solicitar segunda cidade do mesmo IP antes de uma hora: `429` e `Retry-After`.
6. Solicitar depois de uma hora: deve ser admitido se há capacidade.
7. Solicitar uma cidade já concluída: `200` sem recalcular.
8. Testar limite de dez tarefas ativas e ver retorno `503`.
9. Validar identificação espacial com uma, duas e nenhuma grade.
10. Interromper/reiniciar worker e verificar recuperação.
11. Verificar que chave de API de leitura não concede privilégios de escrita.
12. Conferir logs de Nginx para IP real e não `127.0.0.1` em todas as requisições.

**Nenhuma destas configurações da VPS ou migrações foi executada por esta PR.**
