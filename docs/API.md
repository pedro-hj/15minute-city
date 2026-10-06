# API de indicadores

A API FastAPI fornece acesso somente de leitura aos resultados agregados já
persistidos no PostgreSQL/PostGIS. Ela não executa análises geográficas.

## Execução local

Defina pelo menos `DATABASE_URL` e `API_KEYS` no arquivo `.env`:

```env
DATABASE_URL=postgresql+psycopg://user:password@host/database?sslmode=require
API_KEYS=uma-chave-longa-e-aleatoria
```

No Docker Compose, `API_DATABASE_URL` pode ser definida para que apenas o
container da API utilize a conexão somente leitura. Sem ela, o Compose usa
`DATABASE_URL`, o que facilita o desenvolvimento local.

Depois execute:

```bash
uv run fifteen-minute-city-api
```

A documentação interativa estará em `http://localhost:8000/docs`. Clique em
**Authorize** e informe a chave. Em chamadas diretas, envie:

```text
X-API-Key: uma-chave-longa-e-aleatoria
```

Também é possível iniciar o container da API:

```bash
docker compose up --build api
```

## Consultas principais

```text
GET /api/v1/cities
GET /api/v1/categories
GET /api/v1/cities/{city_id}/executions
GET /api/v1/cities/{city_id}/latest
GET /api/v1/cities/{city_id}/history
```

As estratégias públicas são `nodes` e `population`. Exemplos:

```text
GET /api/v1/cities/1/latest/nodes/health/coverage_percentage
GET /api/v1/cities/1/latest/nodes/overall_coverage_percentage
GET /api/v1/cities/1/history/population/health/coverage_percentage
```

As respostas históricas são ordenadas da execução mais recente para a mais
antiga. Apenas execuções com estado `completed` são publicadas.

## Usuário de banco somente leitura

Na produção, a `DATABASE_URL` da API deve apontar para um usuário diferente do
processador. Um administrador pode criar esse usuário no banco com permissões
equivalentes a:

```sql
CREATE ROLE api_reader LOGIN PASSWORD 'troque-esta-senha';
GRANT CONNECT ON DATABASE defaultdb TO api_reader;
GRANT USAGE ON SCHEMA public TO api_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO api_reader;
```

O SQL deve ser adaptado ao nome do banco e executado com uma conta
administrativa. A senha não deve ser versionada no repositório.
