# ИИ-ассистент студента МГТУ — лабораторная №1, редакция 1.1

Исправленный комплект по замечаниям №2–5 от 04.10.2026. Команда: «Министерство нейронных дел».

## Состав

* [docs/project\_description.md](docs/project_description.md) — цель, аудитория, границы, источники и выбранные модели;
* [docs/requirements.md](docs/requirements.md) — требования, целевые 8 ГБ RAM и критерии проверки;
* [docs/use\_cases.md](docs/use_cases.md) — семь сценариев с конкретными шагами RAG;
* [docs/risks.md](docs/risks.md) — риски и пределы программных проверок;
* [docs/architecture.md](docs/architecture.md) — описание компонентов и ответственности;
* [docs/architecture\_v2.png](docs/architecture_v2.png) — обновлённая схема;
* [docs/architecture\_v2.svg](docs/architecture_v2.svg) — редактируемый исходник схемы;
* [docs/review\_responses.md](docs/review_responses.md) — ответы на каждое замечание;
* [docs/defense\_notes.md](docs/defense_notes.md) — тезисы защиты;
* [config/model\_manifest.json](config/model_manifest.json) — модели, ревизии, файлы и SHA-256;
* [config/rag\_config.json](config/rag_config.json) — проектные параметры;
* [ai\_usage/ai\_log.md](ai_usage/ai_log.md) — точный ID модели подготовки текущей редакции и журнал.

## Основные решения

Embeddings — `intfloat/multilingual-e5-small`; генератор — `Qwen2.5-1.5B-Instruct`, GGUF Q4\_K\_M, llama.cpp на CPU. Целевой минимум — 8 ГБ RAM, без обязательной видеокарты. Параметры одинаковы в документах, конфигурации и схеме.

UC-06 реализуется поиском в локальном индексе описаний подразделений: весь вопрос → E5 → FAISS → проверка источника → краткий ответ по найденному тексту. Отдельной классификации темы и агента нет.

Текущая документация подготовлена с OpenAI `gpt-6.1-sol` (версия 6.1) через Codex. Название модели прошлого исходного черновика в архиве не зафиксировано и не приписано ему задним числом.

## Статус

Это лабораторная по проектированию. Модели выбраны и зафиксированы; полный RAG на этих моделях ещё не реализован и не измерялся на 8 ГБ. 

