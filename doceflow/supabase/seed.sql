-- DoceFlow · dados iniciais da Kika Cakes (EXEMPLO: confirmar preços e produtos com a confeitaria)
-- Rodar depois de migrations/001_schema_leads.sql.
--
-- Depois de criar o usuário da dona em Authentication > Users, vincule:
--   update public.confeitarias set owner_user_id = '<uuid do usuário>' where slug = 'kika-cakes';
-- E, quando houver o número oficial:
--   update public.confeitarias set whatsapp = '55DDDNUMERO' where slug = 'kika-cakes';

insert into public.confeitarias (slug, nome)
values ('kika-cakes', 'Kika Cakes')
on conflict (slug) do nothing;

insert into public.produtos
    (confeitaria_id, slug, nome, categoria, descricao, unidade, preco, tipo_preco, disponivel, imagem, qtd_min, qtd_max, ordem)
select c.id, p.slug, p.nome, p.categoria, p.descricao, p.unidade, p.preco, p.tipo_preco, p.disponivel, p.imagem, p.qtd_min, p.qtd_max, p.ordem
from public.confeitarias c
cross join (values
    ('bolo-festa', 'Bolo de festa decorado', 'Bolos',
     'Massa fofinha, recheio à escolha e decoração personalizada com o tema da sua festa.',
     'kg', 120.00, 'a_partir_de', true, 'bolo-festa.svg', 2, 15, 1),
    ('naked-cake', 'Naked cake com frutas', 'Bolos',
     'Camadas aparentes, recheio cremoso e frutas da estação. Ótimo para chás e casamentos.',
     'kg', 140.00, 'a_partir_de', false, 'naked-cake.svg', 2, 10, 2),
    ('cupcakes', 'Cupcakes decorados', 'Cupcakes',
     'Cupcakes com cobertura de buttercream e coraçãozinho, na caixa de presente.',
     'caixa com 6', 48.00, 'a_partir_de', true, 'cupcakes.svg', 1, 30, 3),
    ('brigadeiros', 'Brigadeiros gourmet', 'Doces',
     'Brigadeiros tradicionais e de sabores especiais, em forminhas para festa.',
     'cento', 150.00, 'estimado', true, 'brigadeiros.svg', 1, 20, 4),
    ('bolo-pote', 'Bolo de pote', 'Doces',
     'Camadas de bolo e recheio no pote, para lembrancinhas ou para adoçar o dia.',
     'unidade', 14.00, 'a_partir_de', true, 'bolo-pote.svg', 1, 200, 5),
    ('kit-festa', 'Kit festa na caixa', 'Kits',
     'Bolo, docinhos e cupcakes combinando, montados na caixa para festas pequenas.',
     'kit', null, 'sob_consulta', true, 'kit-festa.svg', 1, 10, 6)
) as p (slug, nome, categoria, descricao, unidade, preco, tipo_preco, disponivel, imagem, qtd_min, qtd_max, ordem)
where c.slug = 'kika-cakes'
on conflict (confeitaria_id, slug) do nothing;
