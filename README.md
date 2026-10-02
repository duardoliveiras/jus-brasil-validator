# Validador de citações BRACIS Jusbrasil

## Rodar

Python 3.11+, sem instalar dependências:

```bash
bash run.sh caminho/base.db caminho/txt saida.csv
```

Exemplo com a amostra incluída:

```bash
bash run.sh files/desafio1_bracis.db files/txt runs/submission.csv
```

Para a avaliação final, substitua o banco e a pasta pelos novos dados. A imagem
contém somente o código, os dados são fornecidos na execução. Não requer GPU,
internet, API e pesos de modelos

## Arquitetura

`TXT → regex → normalização → índices do SQLite → classificação → CSV`

- `baseline.py`: extrai os processos, sumulas, leis e referências vagas e remove sobreposições
- `resolver.py`: reconstrói os índices em memória a cada execução usando o banco
  recebido, sem alterá-lo. Normaliza siglas, números e erros de OCR.
- Registro único: `real` com ID canônico. Identificador completo sem registro:
  `inventada`. Referência vaga ou ambígua: `incompleta`.

Confiança fixa em `1.0`, sem calibração estatistica.
