# OPS-BOE-01: diagnóstico y recuperación preparada

Base: main 23bbb125c972530fd222b1dc0eb2c8cfa01e6ea1. PR #22 independiente.

## Evidencia

Los runs [28 octubre](https://github.com/alexmihaic/HLT-InfoCS/actions/runs/40733290540), [30 octubre](https://github.com/alexmihaic/HLT-InfoCS/actions/runs/41095332315) y [4 noviembre](https://github.com/alexmihaic/HLT-InfoCS/actions/runs/41889462940) terminaron en fallo. Sus manifiestos indican source_failure, transport y seen=0. El [3 noviembre](https://github.com/alexmihaic/HLT-InfoCS/actions/runs/41694145395) terminó correctamente con 237 vistos. El código anterior reduce motivos diversos a source_failure; además captura excepciones internas como pipeline_failure pero las rotula transport. Los datos no identifican si fue red, HTTP, respuesta o error interno; no se puede atribuir al servidor BOE.

## Cambios y límites

Hasta tres intentos con pausas de 1 y 2 segundos solo en timeout y HTTP 429, 500, 502, 503 o 504. No se reintentan formato incorrecto, TLS/otros errores de red, redirecciones, 400 o 404. El resultado final sigue siendo fallido al agotarse intentos. No se exponen mensajes, URLs ni cuerpos de excepción. ErrorSummary conserva esquema y mensaje seguro, con códigos acotados para red, HTTP y formato; excepciones inesperadas se clasifican pipeline_failure/pipeline. 404 conserva semántica preexistente de no_publication. La recuperación no se ha ejecutado.

## Recuperación propuesta — no ejecutar todavía

El workflow `boe-manual.yml` acepta workflow_dispatch con input obligatorio date YYYY-MM-DD. Usa `--date`, valida y puede hacer commit/push en main y desencadenar Pages. Tras integración autorizada y comprobación de ejecución en main, lanzar secuencialmente únicamente con autorización de recuperación:

```
gh workflow run boe-manual.yml --ref main -f date=2026-10-28
gh workflow run boe-manual.yml --ref main -f date=2026-10-30
gh workflow run boe-manual.yml --ref main -f date=2026-11-04
```

Esperar el resultado completo de cada ejecución antes de la siguiente; revisar manifiesto, health, fecha, exit code, cambios canónicos, seguridad de publicación y Pages. No usar Re-run jobs porque reutiliza contexto y fecha de la ejecución original. La concurrencia y comprobación del SHA de main previenen publicaciones concurrentes obsoletas pero no sustituyen la revisión. Ejecutar con fecha antigua puede producir actualizaciones sobre datos presentes; verificar conflictos y procedencia antes de autorizar. Una respuesta 404 solo indica ausencia según la semántica actual, no demuestra que una recuperación haya reconstruido la edición.

## Validación local

- `python -m unittest discover -s tests`: 705 pruebas, OK. Incluye idempotencia de la misma edición y controles existentes de workflow, publicación y preservación de fallos.
- Pruebas focalizadas de transporte, runner y manifiestos: 57 OK; cubren recuperación tras timeout, agotamiento y ausencia de reintentos ante errores permanentes, códigos seguros y excepción interna sin datos privados.
- `git diff --check`: OK. No se han ejecutado collectors ni recuperaciones reales. Pendiente verificar Actions de la PR y el funcionamiento con las condiciones reales de red; no se pretende reproducir retrospectivamente la causa.
