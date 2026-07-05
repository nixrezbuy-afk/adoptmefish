# ДЕПЛОЙ БОТА НА ХОСТИНГЕ

## 🚀 СПОСОБ 1: ЧЕРЕЗ Docker (рекомендуется)

### Локальная сборка:
```bash
# Собираем образ
docker build -t adoptme-spam-bot .

# Запускаем контейнер
docker run -d \
  --name adoptme-bot \
  -v $(pwd)/sessions:/app/sessions \
  -v $(pwd)/tdata:/app/tdata \
  -v $(pwd)/users.db:/app/users.db \
  --env-file .env \
  adoptme-spam-bot