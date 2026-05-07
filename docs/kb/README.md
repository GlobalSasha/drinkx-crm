# Knowledge Base — для навигации в репозитории

Канонические файлы Knowledge Base находятся в:

```
apps/api/knowledge/drinkx/
```

Смотри [`apps/api/knowledge/drinkx/README.md`](../../apps/api/knowledge/drinkx/README.md) для полного описания структуры и логики лоадера.

## Почему файлы не здесь?

Docker build context для API — это директория `apps/api/`. Файлы за пределами этой директории не копируются в образ при `docker build` и недоступны в runtime. Поэтому все операционные файлы KB живут в `apps/api/knowledge/drinkx/`.

Эта директория (`docs/kb/`) существует как точка навигации для читателей репозитория. Контент здесь не дублируется — только этот указатель.
