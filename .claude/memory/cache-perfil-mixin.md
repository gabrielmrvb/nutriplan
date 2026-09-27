---
name: cache-perfil-mixin
description: sob OnboardingRequiredMixin o perfil fica em cache; gravar por outra instância faz o motor ler o valor velho
metadata:
  type: reference
---
O mixin lê o perfil pelo descritor (`request.user.profile`), que fica em
cache para a tela inteira. Quem grava por `Profile.objects.filter(...)
.first()` e depois chama o motor lê o cache velho — a escolha da duração
remontava a ficha para "padrão" (21/09/2026). Grave por
`self.perfil_do_dispatch`/`request.user.profile`, ou apague o cache antes
de o motor ler.

Fonte: CLAUDE.md:2216-2224; accounts/views.py:1220,1241
