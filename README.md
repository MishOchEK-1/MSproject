# Maker Space MVP

Django-приложение для работы Maker Space: пользователи, инструктаж, каталог оборудования, бронирование, подтверждение заявок и внутренние уведомления.

Репозиторий GitHub: [MishOchEK-1/MSproject](https://github.com/MishOchEK-1/MSproject)

## Команда

Команда разработчиков и зоны ответственности проекта:

- Романчев Михаил: главный программист и лидер команды
- Камалов Тилек: бэкенд-разработка
- Рахматулин Айдын: фронтенд-разработка
- Русланов Доолот: бэкенд-разработка и база данных
- Мирбекова Наиля: дизайн и моральная поддержка

## Что важно знать сразу

- текущий рабочий checkout для разработки в этой среде: `/home/cestlavie/Programming/Working/MScontrol`
- канонический локальный контекст проекта лежит в `ProjectLLMContext/`
- для точной картины по структуре и ограничениям сначала смотреть:
  - `ProjectLLMContext/CURRENT/WORKSPACE_STATE.md`
  - `ProjectLLMContext/CURRENT/project_manifest.yaml`

## Что делает проект

- логинит пользователей по email
- хранит роли `guest`, `student`, `staff`, `admin`
- ограничивает бронирование по инструктажу и статусу оборудования
- показывает каталог оборудования и дневную загрузку
- позволяет создавать, продлевать и отменять брони
- использует `pending` и `approved` как активные статусы
- отправляет внутренние уведомления по событиям бронирования
- пишет доменные события в аудит

## Текущий продуктовый контур

Активные пользовательские маршруты:

- `/`
- `/accounts/...`
- `/equipment/...`
- `/notifications/...`
- `/reservations/...`
- `/admin/`

Практическая заметка:

- в текущем clean checkout нет активного пользовательского маршрута `/audit/`
- нет versioned `requirements.txt`
- нет versioned deploy-папки внутри `MScontrol`

## Технологии

- Python
- Django
- SQLite
- Django Templates
- Django Class-Based Views

## Локальный запуск

В clean checkout нет versioned dependency manifest, поэтому способ установки зависимостей должен браться из вашей локальной среды или из `ProjectLLMContext/CURRENT/SETUP_TEST_DEPLOY.md`.

Базовые команды:

```bash
python manage.py migrate
python manage.py runserver
python manage.py check
python manage.py test
```

## Структура

- `MacerSpaceProject/` - настройки и корневой роутинг Django
- `users/` - пользователи, роли, логин, профиль, инструктаж
- `equipment/` - оборудование, downtime, detail и schedule views
- `reservations/` - бизнес-логика бронирования
- `notifications/` - внутренние уведомления
- `audit/` - внутренний слой аудита
- `templates/` - HTML-шаблоны
- `ProjectLLMContext/` - долговечный локальный контекст для следующих сессий

## Замечание по source of truth

Если `README.md` расходится с кодом или с `ProjectLLMContext/CURRENT/WORKSPACE_STATE.md`, приоритет у кода и у `ProjectLLMContext`.
