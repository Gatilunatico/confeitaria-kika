# Schema do banco: diagnóstico e referência

**Diagnóstico feito em 2026-11-14** no Supabase real (projeto `dfimrkfcudidosdldsjv`, região AWS `us-west-2`, PostgreSQL 17.11), **só com consultas de leitura**. Nenhum dado foi alterado.

## 1. Migrações

| Arquivo | Conteúdo | No Supabase |
|---|---|---|
| `migrations/001_schema_leads.sql` | `confeitarias`, `produtos`, `leads`, RLS e função `criar_lead` | ✅ aplicada |
| `migrations/002_painel_admin.sql` | novo funil de status, `status_atualizado_em` e escrita de produtos pela dona | ✅ aplicada |
| `migrations/003_catalogo_real.sql` | 27 produtos oficiais e WhatsApp oficial | ✅ aplicada |
| `migrations/004_marketing.sql` | `marketing_posts` e bucket privado `marketing` | ❌ **não aplicada**: não existe a tabela nem o bucket |
| `seed.sql` | confeitaria e produtos iniciais (para um projeto novo) | conteúdo equivalente já está no banco |

Os nomes dos arquivos foram mantidos. A numeração é a ordem em que as migrações foram aplicadas no banco real, e renomear causaria confusão sobre o que já rodou.

## 2. Tabelas atuais (`public`)

| Tabela | Linhas | RLS | Colunas principais |
|---|---|---|---|
| `confeitarias` | 1 | ativa | `id`, `slug`, `nome`, `whatsapp`, `owner_user_id` → `auth.users`, `ativo`, `created_at`, `updated_at` |
| `produtos` | 27 | ativa | `id`, `confeitaria_id`, `slug`, `nome`, `categoria`, `descricao`, `unidade`, `preco`, `tipo_preco`, `disponivel`, **`imagem` (nome de arquivo em `assets/default_images`)**, `qtd_min`, `qtd_max`, `ordem`, timestamps |
| `leads` | 3 (todos "Novo") | ativa | `id`, `protocolo`, `confeitaria_id`, `produto_id`, `produto_nome`, `unidade`, `quantidade`, `data_desejada`, `modalidade`, `observacoes`, `cliente_nome`, `cliente_whatsapp`, `consentimento`, `consentimento_em`, `origem`, `status`, `status_atualizado_em`, `fingerprint`, timestamps |
| `leads_antiga` | 0 | ativa | tabela antiga renomeada em 07/11. **Não é usada** e pode ser removida quando você decidir |

- **Funções:** `criar_lead` (SECURITY DEFINER, única escrita pública), `set_updated_at` e `set_status_atualizado_em`.
- **Status de lead:** Novo, Em atendimento, Orçamento enviado, Venda concluída e Perdido.
- **Auth:** 2 usuários, e a Kika Cakes tem dona vinculada.
- **Storage:** nenhum bucket.

## 3. Permissões (RLS)

| Tabela | anon (cliente) | authenticated (dona) |
|---|---|---|
| `confeitarias` | lê as ativas | lê |
| `produtos` | lê | lê, cria e edita só na própria confeitaria (sem mudar `slug` nem confeitaria) |
| `leads` | **sem acesso**: cria só via `criar_lead` | lê e altera o `status` só da própria confeitaria |

## 4. Lacunas para as próximas funcionalidades (nada foi implementado)

| Funcionalidade pedida | O que falta no banco |
|---|---|
| **Upload de fotos de produtos** | Um bucket público de leitura (por exemplo `produtos`) com escrita só da dona, e uma coluna para o caminho ou URL da foto em `produtos`. Hoje `imagem` só aponta para arquivos do repositório |
| **Cadastro de produtos pela área admin** | Já existe (INSERT/UPDATE com RLS). Falta apenas a exclusão ou o arquivamento, se for desejado |
| **Gerenciamento de pedidos** | Uma tabela `pedidos` (e itens, se houver mais de um produto), ligada ao lead de origem, com valor combinado, sinal, data de entrega e status de produção. **Não existe hoje**: o funil para em "Venda concluída" |
| **Estúdio de Marketing no Supabase** | Aplicar `004_marketing.sql` |
| **Integração com Instagram** | Nenhuma estrutura. Exigiria tokens da API da Meta guardados com segurança, fora do código |

**Recomendação:** antes de criar as migrações novas, definir com a proprietária o fluxo do pedido (o que acontece depois da "Venda concluída") e quem pode ver o quê.
