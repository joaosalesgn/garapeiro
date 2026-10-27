INSERT INTO tab_produto_adicional (
    criado_em,
    atualizado_em,
    atualizado_por_id,
    adicional_id,
    produto_id,
    criado_por_id
)
SELECT
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    origem.atualizado_por_id,
    origem.adicional_id,
    destino.produto_id,
    origem.criado_por_id
FROM tab_produto_adicional AS origem
CROSS JOIN (
    SELECT 16 AS produto_id UNION ALL
    SELECT 17 UNION ALL
    SELECT 18 UNION ALL
    SELECT 19 UNION ALL
    SELECT 20 UNION ALL
    SELECT 21 UNION ALL
    SELECT 22 UNION ALL
    SELECT 23 UNION ALL
    SELECT 24 UNION ALL
    SELECT 25 UNION ALL
    SELECT 26
) AS destino
JOIN tab_produto AS produto
    ON produto.id = destino.produto_id
WHERE origem.produto_id = 1
  AND NOT EXISTS (
      SELECT 1
      FROM tab_produto_adicional AS existente
      WHERE existente.produto_id = destino.produto_id
        AND existente.adicional_id = origem.adicional_id
  );