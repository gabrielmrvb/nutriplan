---
name: agent-browser-127
description: contra o runserver local, use http://127.0.0.1:8000 — localhost dá ERR_CONNECTION_REFUSED no agent-browser
metadata:
  type: reference
---
Medido em 27/09/2026: o Chrome do agent-browser resolve `localhost` para
`::1` (IPv6) e o `runserver` escuta só em `127.0.0.1`, então
`http://localhost:8000` responde ERR_CONNECTION_REFUSED com o servidor de
pé. Use `http://127.0.0.1:8000`.

Fonte: medição de 27/09/2026 (sem arquivo no repositório)
