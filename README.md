# Nardy

Стартовый репозиторий командного проекта по игре «Нарды» на Python 3.12.

Репозиторий подготовлен как архитектурная и инфраструктурная основа для командной разработки через pull request. В нём уже заложены:

* `src`-layout и wheel-сборка;
* автоматизация через `doit`;
* линтеры, тесты и покрытие;
* документация на Sphinx;
* локализация через Babel;
* разделение на слои `app`, `domain`, `ui`, `net`, `i18n`.

## Цели стартового каркаса

Каркас должен помочь команде двигаться независимо и без конфликтов по слоям:

* разработчик 1 закладывает архитектуру, инфраструктуру и границы модулей;
* разработчик 2 реализует локальную игру, правила и tkinter GUI;
* разработчик 3 добавляет LAN-режим через сокеты и финализирует демонстрационный сценарий.

## Технологический стек

* Python 3.12
* tkinter
* flake8
* pydocstyle
* pytest
* pytest-cov
* Sphinx
* Babel
* doit
* build

## Структура проекта

```text
Project_Nards/
├── docs/
├── src/
│   └── nardy/
│       ├── app/
│       ├── domain/
│       ├── i18n/
│       ├── net/
│       └── ui/
├── tests/
├── .github/
├── babel.cfg
├── dodo.py
└── pyproject.toml
```

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
python -m doit check
```

Для запуска приложения используется entry point:

```bash
nardy
```

Для локальной игры в двух отдельных процессах через сокеты:

```bash
nardy --server --socket-host 127.0.0.1 --socket-port 8765 --locale ru
nardy --join --socket-host 127.0.0.1 --socket-port 8765 --locale ru
```

## Команды автоматизации

```bash
python -m doit lint
python -m doit test
python -m doit coverage
python -m doit docs
python -m doit build
python -m doit babel_extract
python -m doit babel_update
python -m doit babel_compile
python -m doit check
```

## Архитектурные принципы

* Доменные сущности не зависят от tkinter.
* Сетевой слой не знает о внутренней реализации UI.
* Undo проектируется на уровне состояния игры.
* Режимы длинных и коротких нард подключаются через единый интерфейс правил.
* Приложение готовится к локальной игре и дальнейшему LAN-расширению без переписывания доменного слоя.

## Документация

Содержимое папки `docs/`:

* `architecture.rst` — архитектурные решения и границы слоёв;
* `developer_guide.rst` — локальная разработка и соглашения;
* `workflow.rst` — командный workflow через PR.

## Статус

Этот репозиторий — стартовый каркас. Полные правила, игровая логика, сетевое взаимодействие и финальный GUI будут добавляться следующими итерациями команды.
