# Etapa 04 — Painel administrativo do DoceFlow

Data: 07/11/2026. Branch de implementação: `dev`.

## Implementação

- Login obrigatório com `ADMIN_PASSWORD`, comparação em tempo constante e logout. Sem senha configurada, o painel é bloqueado. Nenhum repositório administrativo é consultado antes do login.
- Sessão vinculada à senha, ao banco e ao `STORE_ID` do servidor; uma antiga flag `admin_ok` não concede acesso.
- Lista de solicitações com protocolo, nome, produto, data de registro, data desejada, contato e status. Detalhes incluem quantidade, entrega/retirada e observações.
- Filtros por status e período de registro, com extremos inclusivos e validação da ordem das datas.
- Status persistentes: Novo, Em atendimento, Orçamento enviado, Venda concluída e Perdido.
- Venda concluída exige confirmação manual adicional. Uma solicitação pública sempre entra como Novo.
- Link de WhatsApp para o contato e protocolo da solicitação. Abrir o link não muda status e não confirma envio de mensagem.
- Cadastro e edição de produtos, preços, tipo de preço, disponibilidade, descrição, categoria, unidade e limites de quantidade. A vitrine lê o mesmo banco.
- Indicadores sobre o conjunto filtrado: total, novos, orçamentos enviados, vendas e conversão. Conversão = vendas concluídas / total × 100; sem leads, 0%. Os indicadores representam status atuais, não histórico de mensagens.
- SQLite em arquivo com todas as leituras e alterações restritas ao identificador da confeitaria. Deduplicação também é restrita à confeitaria.

## Evidências automatizadas

Somente dados sintéticos são usados nos testes; cada teste recebe um banco temporário.

| Critério | Evidência / teste em `tests/test_etapa04.py` |
|---|---|
| Acesso administrativo protegido | `test_auth_blocks_data_and_fake_legacy_session`: sem login ou senha configurada, sem tabela, indicadores ou abas; senha errada rejeitada; flag antiga ignorada. |
| Sessão não atravessa confeitaria/senha | `test_auth_scope_and_rotation`: alteração do identificador muda o token; senha antiga deixa de autenticar após rotação. |
| Novos leads identificáveis | `test_admin_ui_manual_status_and_logout`: solicitação recém-criada aparece na tabela e nos indicadores total=1 e novos=1. |
| Venda depende de confirmação | O mesmo teste tenta salvar venda sem confirmar, recebe erro, confirma e salva; o banco registra venda e a interface mostra vendas=1 e conversão=100%. |
| Todos os status persistem | `test_restart_status_filters_and_metrics`: percorre os cinco status e verifica cada alteração com uma nova instância do repositório. Status desconhecido é rejeitado. |
| Indicadores corretos | Dois leads, sendo uma venda e um orçamento enviado: total=2, novos=0, orçamentos enviados=1, vendas=1, conversão=50%. Sem leads, conversão=0%. |
| Filtros operacionais | Testes de serviço e `test_admin_ui_filters` verificam status, período, datas inclusivas e conjunto vazio. |
| WhatsApp não é comprovante de envio | Teste de interface verifica destino `wa.me/5511987654321`; somente salvar status altera o atendimento. Não há API de envio nem confirmação automática. |
| Produtos sem alterar fonte | `test_product_persistence_public_catalog_and_validation`: muda preço para R$87,50 e disponibilidade, verifica o catálogo público, cadastra produto e reabre o repositório. Dados inválidos são rejeitados. `test_admin_ui_product_creation` cadastra pela interface. |
| Isolamento de confeitarias | `test_tenant_isolation`: loja B não vê leads de A nem altera seu status; preço e nome de produtos são isolados. |
| Reinício real de processo | `test_restart_in_fresh_process`: grava lead e venda, inicia outro interpretador com o mesmo banco e confirma a leitura do status persistido. |
| Sem fallback de banco | `test_backend_fails_closed`: modo Supabase é rejeitado explicitamente, sem usar outro banco. |

## Como reproduzir

Na pasta `doceflow`, com dependências de `requirements.txt` instaladas:

```text
python -m pytest -q
python -m compileall -q app.py pages services tests
```

Para operação: configure `ADMIN_PASSWORD`, `STORE_ID`, `DB_BACKEND=sqlite` e `SQLITE_PATH`; execute `streamlit run app.py`, abra **admin**, entre, altere um status e um produto, encerre a aplicação e abra novamente. O arquivo SQLite precisa permanecer no mesmo caminho.

## Limites e decisões

- Esta etapa implementa persistência SQLite. O código anterior tinha apenas criação do cliente Supabase, sem tabelas/repositórios de negócio. Não foi afirmada nem validada persistência remota Supabase.
- Use uma implantação e uma senha exclusiva por confeitaria. `STORE_ID` é configuração privada do servidor, não um seletor público. O painel não implementa contas individuais ou recuperação de senha.
- O arquivo SQLite requer disco persistente e backup; hospedagem com disco efêmero não garante conservação após recriar a instância.
- Solicitações antigas que existiam somente na memória não são migráveis depois de perder a sessão. Novas solicitações são persistidas automaticamente.
- Produtos novos recebem ilustração padrão. Não há gráficos decorativos, disparo de mensagens ou conversão automática em venda.
- Evidências de interface foram executadas com Streamlit AppTest; não representam uma inspeção visual em navegador nem testes de implantação em produção.

## Resultado da validação

Execução completa em 07/11/2026:

```text
54 passed in 44.06s
```

Ambiente: Python 3.12, pytest 8.4.2, Streamlit 1.67.0 e Pandas 2.3.3 (dentro das faixas do projeto). A suíte inclui as etapas 01, 02 e 04. A primeira execução identificou apenas um timeout de inicialização da tabela; os testes novos passaram a usar limite de 60 segundos, e a suíte completa foi repetida com sucesso.

Compilação dos módulos e verificação de espaços do diff também concluídas sem erros.
