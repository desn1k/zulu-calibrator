# Развёртывание на сервере

Пошаговая инструкция: от пустого VPS до работающего сайта по HTTPS. Команды выполняются на сервере
по SSH; их можно копировать целиком. Там, где нужно подставить своё значение, оно выделено так:
`calib.example.org` — ваш домен, `v0.1.0-rc1` — версия.

## 1. Что нужно заранее

**Сервер (VPS):**

| Параметр | Значение |
| --- | --- |
| Система | Ubuntu 24.04 LTS (чистая установка) |
| Процессор | 2 vCPU |
| Память | 2–4 ГБ RAM |
| Диск | 30–40 ГБ SSD |
| Сеть | публичный IPv4-адрес; открыты порты 22 (SSH), 80 и 443 |

**Домен** (или поддомен), например `calib.example.org`, и доступ к его настройкам DNS.

## 2. Направить домен на сервер

В панели DNS регистратора (или хостинга DNS) создайте запись:

| Тип | Имя | Значение |
| --- | --- | --- |
| A | `calib` (или `@` для корневого домена) | IP-адрес сервера |

Изменение расходится от нескольких минут до нескольких часов. Проверить можно с любого компьютера:

```sh
nslookup calib.example.org
```

В ответе должен быть IP вашего сервера. Пока его нет, сертификат HTTPS не выпустится — дальше
идти можно, но проверку (шаг 8) делайте после того, как DNS заработал.

## 3. Подготовить сервер

Подключитесь по SSH и обновите систему:

```sh
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git
```

Включите файрвол и откройте только нужные порты (SSH — первым, чтобы не потерять доступ):

```sh
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

## 4. Установить Docker

Официальный репозиторий Docker для Ubuntu:

```sh
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Разрешите своему пользователю запускать Docker без `sudo`, затем **выйдите из SSH и зайдите снова**:

```sh
sudo usermod -aG docker "$USER"
```

Проверка после повторного входа:

```sh
docker compose version
```

## 5. Скачать приложение

```sh
sudo mkdir -p /opt/zulu-calibrator
sudo chown "$USER": /opt/zulu-calibrator
git clone https://github.com/desn1k/zulu-calibrator.git /opt/zulu-calibrator
cd /opt/zulu-calibrator
git checkout v0.1.0-rc1
```

`git checkout` переключает на ту версию, которую выкатываем (её номер даёт Андрей). Если репозиторий
закрытый, `git clone` попросит логин и токен доступа GitHub.

Все дальнейшие команды выполняются из папки `/opt/zulu-calibrator`.

## 6. Заполнить `.env`

```sh
cp .env.example .env
chmod 600 .env
nano .env
```

| Переменная | Что вписать |
| --- | --- |
| `DOMAIN` | ваш домен, например `calib.example.org` |
| `ACME_EMAIL` | по желанию: почта для уведомлений Let's Encrypt о сертификате; можно оставить пустой |
| `IMAGE_TAG` | версия, та же, что в `git checkout`, например `v0.1.0-rc1` (никогда не `latest`) |
| `SECRET_KEY` | случайная строка, см. команду ниже |
| `DATABASE_URL` | не трогать (в Docker путь к базе задан в `docker-compose.yml`) |
| `LOG_LEVEL` | `info` |

`SECRET_KEY` сгенерировать так и вставить результат после `SECRET_KEY=`:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Сохранить в `nano`: `Ctrl+O`, `Enter`, выйти: `Ctrl+X`. Файл `.env` содержит секреты — не
пересылайте его и не добавляйте в git.

## 7. Запустить

```sh
docker compose up -d --build
```

Первая сборка занимает несколько минут. Образ собирается прямо на сервере, внешний реестр образов не
нужен. Посмотреть состояние:

```sh
docker compose ps
```

Должно быть три сервиса, все в статусе `healthy`: `app`, `caddy` и `backup`. У `backup` статус `healthy` значит, что последняя копия базы моложе 26 часов.

## 8. Проверить

```sh
curl https://calib.example.org/healthz
```

Ответ `{"status":"ok","db":"ok"}` — сайт работает, база доступна. Откройте `https://calib.example.org`
в браузере: замок в адресной строке, страница «Калибровка ЦТП». Адрес с `http://` автоматически
переводится на `https://`.

Если не работает:

| Признак | Что проверить |
| --- | --- |
| ошибка сертификата / соединения | DNS (шаг 2) указывает на этот сервер; порты 80 и 443 открыты у хостера и в `ufw`; `docker compose logs caddy` |
| `app` не `healthy` | `docker compose logs app` |
| `backup` не `healthy` | копии не делаются: `docker compose logs backup` |
| ответ 502 | приложение ещё запускается — подождать минуту и повторить |

## 9. Резервные копии

Сервис `backup` раз в сутки (и при каждом своём запуске) делает копию базы командой `sqlite3 .backup`,
проверяет её (`PRAGMA integrity_check`) и хранит **14 последних** копий. Копии лежат в Docker-томе
`zulu-calibrator_backups`, внутри контейнера — в папке `/backups`, имена вида
`app-20261014T030000Z.db` (дата и время UTC).

Посмотреть список копий:

```sh
docker compose exec backup ls -l /backups
```

Сделать копию прямо сейчас:

```sh
docker compose exec backup backup.sh --once
```

Скачать копию с сервера (сначала в папку на сервере, затем к себе, например через `scp`):

```sh
docker compose cp backup:/backups/app-20261014T030000Z.db ./
```

Копии на том же сервере не спасут при потере сервера — периодически скачивайте свежую копию к себе.

## 10. Восстановить базу из копии

1. Сохранить текущее состояние (на случай, если понадобится вернуться) и выбрать нужную копию:

   ```sh
   docker compose exec backup backup.sh --once
   docker compose exec backup ls -l /backups
   ```

   Если копия лежит у вас на компьютере, сначала загрузите её на сервер (`scp`) и положите в том копий:

   ```sh
   docker compose cp ./app-20261014T030000Z.db backup:/backups/
   ```

2. Остановить приложение и сервис копий:

   ```sh
   docker compose stop app backup
   ```

3. Заменить базу копией (подставьте имя файла):

   ```sh
   docker compose run --rm --no-deps --entrypoint sh backup -c '
     f=/backups/app-20261014T030000Z.db
     test "$(sqlite3 "$f" "PRAGMA integrity_check;")" = ok &&
     cp "$f" /data/app.db && rm -f /data/app.db-wal /data/app.db-shm && echo restored'
   ```

   Должно напечататься `restored`.

4. Запустить всё обратно и проверить:

   ```sh
   docker compose up -d
   curl https://calib.example.org/healthz
   ```

При запуске приложение само доводит структуру базы до текущей версии (миграции), поэтому копия от
более старой версии тоже подходит.

## 11. Обновление до новой версии

```sh
cd /opt/zulu-calibrator
docker compose exec backup backup.sh --once
git fetch --tags
git checkout v0.1.1
nano .env            # IMAGE_TAG=v0.1.1
docker compose up -d --build
```

## 12. Полезные команды

| Команда | Что делает |
| --- | --- |
| `docker compose ps` | состояние сервисов |
| `docker compose logs -f app` | журнал приложения (выход — `Ctrl+C`) |
| `docker compose restart app` | перезапуск приложения |
| `docker compose down` | остановить всё (данные и копии сохраняются в томах) |
| `docker compose up -d` | запустить снова без пересборки |

Не выполняйте `docker compose down -v` — флаг `-v` удаляет тома, то есть базу, копии и сертификаты.
