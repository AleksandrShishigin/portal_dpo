# Портал ДПО — исходники для совместной разработки

Django/DRF, React/TypeScript/Vite, PostgreSQL. Включены актуальные миграции 0001–0008, заявления DOCX, регистрация договоров и реестр с вкладками подписания. Реальная электронная подпись пока не подключена. Рабочие данные и учётные записи не включены.

## Требования
Python 3.11+, Node.js 22.18+ с npm и PostgreSQL 16+. Для отдельного сценария конкурентных тестов на Windows нужен PostgreSQL 18.

## Установка (PowerShell, из этой папки)

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    cd frontend
    npm.cmd ci
    cd ..

## Новая база
Откройте SQL Shell PostgreSQL или psql -U postgres. Создайте отдельную пустую базу и роль:

    CREATE ROLE dpo_classroom_app LOGIN;
    \password dpo_classroom_app
    CREATE DATABASE dpo_classroom OWNER dpo_classroom_app;
    \q

Команда \password интерактивно запросит ваш новый пароль. Не используйте чужую рабочую базу. Если имена заняты, выберите другие и укажите их в .env.

    Copy-Item .env.example .env

Заполните DB_PASSWORD своим паролем, проверьте порт, имя базы и роль. DJANGO_SECRET_KEY можно оставить пустым: приложение создаст личный ключ в .local/django-secret. Не передавайте .env, ключ и базу.

DPO_PROTOTYPE=true включает учебный текст согласия и обязательную галочку для проверки подачи. Используйте вымышленные данные. Почта отключена. Для реального применения потребуются согласованные настройки.

## Миграции, тестовые программы и оператор

    .\.venv\Scripts\python.exe backend\manage.py migrate
    .\.venv\Scripts\python.exe backend\manage.py seed_programs
    .\.venv\Scripts\python.exe backend\manage.py create_operator

seed_programs добавляет три явно вымышленные программы с требованиями, без людей и документов. Повторный запуск сохраняет имеющиеся записи. create_operator интерактивно запрашивает email, имя, фамилию и пароль со скрытым вводом. Общего пароля нет.

## Запуск

    powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1

Портал: http://127.0.0.1:5173/ . API: http://127.0.0.1:8000/api/session/ .
Ctrl+C останавливает оба сервера. Порты 5173 и 8000 должны быть свободны. Используйте адрес 127.0.0.1.

На Linux/macOS используйте python3 -m venv .venv, .venv/bin/python вместо Windows-пути и npm вместо npm.cmd. Запускайте .venv/bin/python scripts/dev.py.

## Проверка сценария
Зарегистрируйте обучающегося через интерфейс. Заполните профиль вымышленными данными, создайте заявку, добавьте тестовые вложения согласно требованиям программы и отправьте заявку с согласием.
Войдите оператором, примите заявку, заполните черновик договора и зарегистрируйте его. В реестре доступны поиск, DOCX и вкладки «Не подписанные» / «Подписанные». Кнопка «Подписать» показывает сообщение о будущем подключении сервиса, без изменения данных.
У существующих программ вид и форма обучения настраиваются оператором в разделе реквизитов программ. Новые программы seed_programs уже имеют эти поля.

## Тесты и сборка
Серверные тесты на чистой SQLite в памяти, без рабочей базы:

    .\.venv\Scripts\python.exe backend\manage.py test portal.tests portal.test_workflows.ExtendedWorkflowTests portal.test_migrations portal.test_profile_documents portal.test_generated_documents portal.test_contract_signatures --settings=config.test_settings
    cd frontend
    npm.cmd run build
    cd ..

Проверка конкурентных операций на отдельном PostgreSQL 18 (Windows):

    .\.venv\Scripts\python.exe scripts\test-postgres.py

Скрипт создаёт изолированный кластер .local/pg-tests на 127.0.0.1:55439 и останавливает его после тестов. Не запускайте Django-тесты с настройками рабочей базы.

## Состав
backend — API, модели, миграции и тесты. frontend — исходники и ресурсы оформления с лицензией шрифтов. scripts/dev.py и start-local.ps1 — запуск. scripts/test-postgres.py — изолированные тесты.
backend/portal/document_templates/contract.docx и statement.docx — чистые шаблоны с токенами, без данных обучающихся. Метаданные авторов очищены. Публичные реквизиты университета и текст шаблонов сохранены.

Документы и снимки появляются только после действий в вашей установке и хранятся в закрытом private-media. Реестры начинаются с пустой базы. Пароли и реквизиты в тестовом коде — явно вымышленные фикстуры, не реальные учётные данные.

История Git, .env, ключи, базы, документы пользователей, архивы и установленные зависимости не включены. Репозиторий Git при необходимости создайте самостоятельно. Ничего автоматически не публикуется.
