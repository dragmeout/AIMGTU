# Лабораторная №4 — Климов Иван

Ваш блок: **Безопасность, калькулятор и ограничения инструментов**. Прежде чем сдавать работу, проверьте эти файлы и укажите фактически выполненные вами действия.

## Для защиты

Климов Иван — Проверены 16 атак, четыре безвредных контроля и 10 случаев вызова функций. У A успешны 4 атаки, у B — 0. В B остаётся обход через Base64 и ложная блокировка цитаты. Реальных секретов не было, файл личных оценок инструментам недоступен. Калькулятор не выполняет Python-код.

## Как объединить части

Распакуйте все пять архивов в одну папку. В каждом используется корень AIMGTU-lab4; файлы распределены без повторов. После объединения откройте README.md. Для запуска всей системы нужны материалы всех пяти участников. Полный архив также содержит весь проект сразу.

В вашем архиве находится ваш блок исходных файлов. Основной README и запуск — у Домашева; описание архитектуры и загрузчик моделей — у Чуракова; корпус и справочник — у Карули; ответы A/B и метрики — у Замиралова; безопасность и тесты — у Климова.

## Ваши файлы

- `data/evaluation/security_cases.jsonl`
- `docs/security_tests.md`
- `experiments/memory_limits.md`
- `experiments/protocol_versions/security_runner_initial.py`
- `experiments/results/memory_16gib.log`
- `experiments/results/memory_16gib_responses.json`
- `experiments/results/memory_8gib.log`
- `experiments/results/memory_8gib_responses.json`
- `experiments/results/memory_limits.json`
- `experiments/results/memory_probe.log`
- `experiments/results/security.json`
- `experiments/results/security_initial.json`
- `experiments/results/security_responses.jsonl`
- `experiments/results/security_responses_initial.jsonl`
- `experiments/results/security_started.json`
- `scripts/memory_worker.py`
- `scripts/run_memory_tests.py`
- `scripts/run_security.py`
- `scripts/windows_job.py`
- `src/security/__init__.py`
- `src/security/policy.py`
- `src/tools/calculator.py`
- `src/tools/registry.py`
- `tests/fixtures/private_store.json`
- `tests/test_tools.py`
