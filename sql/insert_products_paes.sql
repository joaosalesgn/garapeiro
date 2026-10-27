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
    SELECT 33 AS produto_id
    UNION ALL SELECT 34
    UNION ALL SELECT 35
    UNION ALL SELECT 36
    UNION ALL SELECT 38
) AS destino
WHERE origem.produto_id = 3
  AND origem.adicional_id IN (13, 14, 15, 16, 17, 18)
  AND NOT EXISTS (
      SELECT 1
      FROM tab_produto_adicional AS existente
      WHERE existente.produto_id = destino.produto_id
        AND existente.adicional_id = origem.adicional_id
  );