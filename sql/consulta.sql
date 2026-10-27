SELECT pa.produto_id, pa.adicional_id, a.nome
FROM tab_produto_adicional AS pa
JOIN tab_adicional AS a ON a.id = pa.adicional_id
WHERE pa.produto_id = 3
  AND pa.adicional_id IN (13, 14, 15, 16, 17, 18)
ORDER BY pa.adicional_id;


SELECT produto_id, COUNT(*) AS quantidade_adicionais
FROM tab_produto_adicional
WHERE produto_id = 1
GROUP BY produto_id
ORDER BY produto_id;

SELECT id, nome
FROM tab_produto
WHERE id BETWEEN 16 AND 26
ORDER BY id;

SELECT type, name, sql
FROM sqlite_master
WHERE (type = 'table' AND name IN (
    'tab_produto_adicional',
    'tab_produto',
    'tab_adicional'
))
OR (tbl_name = 'tab_produto_adicional' AND type IN ('index', 'trigger'))
ORDER BY type, name;




SELECT name
FROM sqlite_master
WHERE type = 'table'
ORDER BY name;