# Atualização — integração Supabase e resolução dos conflitos

Data: 07/11/2026. Esta atualização se refere à versão integrada da branch `dev`, posterior ao diagnóstico inicial do relatório da etapa 05.

## Resultado

- Resolvidos os quatro conflitos: `pages/admin.py`, `services/catalog.py`, `services/auth.py` e `services/repository.py`. O índice do Git não contém mais entradas não mescladas. A camada antiga de repositório foi retirada e o painel usa o mesmo modelo de banco da vitrine.
- Preservadas as funcionalidades da implementação mais recente já integrada na `dev`: produtos, leads, status, filtros, métricas e Supabase Auth.
- Supabase definido como backend padrão. Não há fallback automático para SQLite. O backend SQLite permanece somente para testes explicitamente configurados.
- Leitura corrigida do `.env` na raiz do repositório, além de `doceflow/.env`; arquivo de credenciais protegido no `.gitignore` da raiz.
- Consulta real, somente leitura, ao Supabase configurado confirmou a confeitaria e **27 produtos**. A chave foi identificada como publicável. Nenhuma credencial foi registrada neste documento.
- O painel restringe o login à confeitaria de `STORE_SLUG`, revalida a conta na sessão e invalida o acesso quando muda a configuração. Campos de credenciais não aparecem na representação textual de Settings.
- A proprietária ainda não foi vinculada em `owner_user_id`. Conforme a orientação do usuário, **conta e vínculo administrativos foram simulados nos testes**, sem cadastrar usuário ou alterar dados no projeto real. O painel real continua exigindo Supabase Auth e vínculo de proprietária.
- Foram preservadas as migrações canônicas `001_schema_leads.sql` e `002_painel_admin.sql`. Não foi executada nenhuma migração remota, seed, mudança de permissão ou operação de escrita no Supabase.

## Validação

Execução completa na pasta `doceflow`:

```text
python -m pytest -q
116 passed, 2 skipped in 26.85s
```

Log: [supabase_integracao_pytest.txt](supabase_integracao_pytest.txt).

Os dois módulos ignorados dependem de PostgreSQL/pgserver local indisponível neste ambiente. Os testes que exercitam Supabase usam respostas simuladas do SDK; a verificação remota foi restrita à leitura do catálogo. Não se afirma que login administrativo real, RLS em produção ou escrita remota tenham sido validados.

Os novos cenários verificam: mudança de confeitaria invalida sessão; registro público recuperável pelo mesmo modelo usado pelo painel; credenciais ocultas em Settings; login Supabase rejeita senha errada; login simulado permitido somente para a confeitaria configurada; sessão expirada volta ao login sem dados administrativos; consulta da proprietária inclui identificação da conta, confeitaria e estado ativo.

`git ls-files -u` ficou vazio. Verificações de espaços do diff passaram. As resoluções foram marcadas no Git; ainda existem alterações locais para revisão. Não houve commit, push ou novo pull.

O relatório inicial permanece como registro do defeito encontrado antes da integração. Seus resultados reprovados não descrevem esta versão corrigida; as limitações de validação remota acima continuam válidas.
