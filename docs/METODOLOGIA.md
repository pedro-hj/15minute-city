# Metodologia de acessibilidade

## Objetivo

O sistema estima a parcela da população que consegue alcançar serviços
essenciais a pé dentro de um limiar configurável, inicialmente 15 minutos.
Os serviços são agrupados em saúde, educação, alimentação e cultura.

## Rede caminhável

O PBF é recortado pelo limite municipal. Vias potencialmente caminháveis são
filtradas pelo Osmium e convertidas em um grafo direcionado. Cada aresta recebe
um tempo de percurso calculado a partir de seu comprimento e da velocidade de
caminhada configurada. Restrições explícitas, como `foot=no` e
`access=private`, são respeitadas, salvo quando existe permissão específica
para pedestres.

O grafo é armazenado em cache. A identidade do cache considera o conteúdo do
PBF, a geometria do limite, o tipo de rede e a versão do construtor.

## Serviços essenciais

Elementos do OpenStreetMap são extraídos por pares de tags e agrupados nas
categorias de domínio. Cada geometria é reduzida a um ponto representativo e
associada ao nó mais próximo da rede caminhável.

## Origens populacionais

A grade populacional é recortada automaticamente pelo limite municipal. São
mantidas as células cujo ponto representativo está coberto pelo município e
cuja população é positiva. Cada célula é associada ao nó mais próximo do
grafo, preservando sua população como peso.

Também é criada uma análise de referência em que cada nó do grafo possui peso
1. Essa referência permite quantificar o viés da abordagem espacial não
ponderada.

## Cálculo de menor tempo

Para cada categoria, o Dijkstra com múltiplas fontes calcula o menor tempo
entre todos os nós alcançáveis e o serviço mais próximo. Em grafos dirigidos,
o cálculo ocorre sobre uma visão invertida da rede para representar o percurso
da origem até o serviço.

Uma origem é:

- alcançável quando existe uma rota até um serviço da categoria;
- atendida quando existe rota e o tempo é menor ou igual ao limiar;
- inalcançável quando não existe rota.

## Indicadores

Para uma categoria `c`:

```text
cobertura(c) = peso atendido dentro do limiar / peso total × 100

inalcançabilidade(c) = peso sem rota / peso total × 100

score(c) = cobertura(c)
```

A média e a mediana dos tempos são ponderadas pela população e consideram
somente origens alcançáveis. A cobertura geral exige que a origem esteja
dentro do limiar em todas as categorias analisadas. A inalcançabilidade geral
inclui origens sem rota para pelo menos uma categoria.

## Comparação

O relatório populacional é comparado ao relatório por nós em pontos
percentuais:

```text
delta = percentual populacional - percentual por nós
```

Essa diferença mostra quanto a distribuição da população altera o diagnóstico
em relação a uma análise que trata igualmente áreas vazias e densamente
habitadas.

## Limitações

- A velocidade é uniforme em toda a rede.
- A qualidade depende da cobertura das tags do OpenStreetMap.
- O ponto representativo simplifica a distribuição interna de cada célula.
- Barreiras não mapeadas e condições temporárias das vias não são consideradas.
- O indicador mede proximidade pela rede, não capacidade ou qualidade do serviço.
