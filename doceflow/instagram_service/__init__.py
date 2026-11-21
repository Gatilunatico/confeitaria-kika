"""Serviço do Instagram do DoceFlow (independente do app e da API de marketing).

Duas partes, no mesmo pacote:
- app.py: autorização OFICIAL da Meta (Instagram API com login do Instagram). A dona toca em
  "Conectar" no app, autoriza na página da Meta e a Meta devolve um código para este serviço,
  que troca pelo token e guarda no Supabase Vault.
- worker.py: publicador. Pega a fila (instagram_publications), publica pela Graph API oficial,
  com tentativas controladas, registro de cada passo e renovação do token antes de vencer.

O token NUNCA vai para o app, para o navegador, para os logs nem para o repositório.
Este serviço roda só no servidor, com credenciais próprias (ver docs/app_mobile/instagram.md).
"""
