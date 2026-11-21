"""API do DoceFlow para o app da confeiteira (Flutter).

Pela arquitetura aprovada, o app fala DIRETO com o Supabase (login, produtos, fotos, orçamentos,
pedidos, clientes e indicadores), sempre com o token da usuária e protegido pelo RLS. Esta API
existe só para o que precisa de Python no servidor: gerar as artes e legendas do Estúdio de
Marketing, reaproveitando o código de `marketing/`.

Regras de segurança:
- Toda rota (menos /v1/saude) exige `Authorization: Bearer <token da sessão do Supabase>`.
- O token é conferido no Supabase Auth a cada pedido e a confeitaria vem do perfil administrativo
  ATIVO da usuária. O banco aplica o RLS com esse mesmo token.
- A API usa só a chave publishable. Ela não tem, não lê e não aceita a chave service_role.
"""
