# Pattern crawler (browser-use + OpenAI)

Скрипт обходит сайты с выкройками и сохраняет:
- фото готового изделия (несколько ракурсов);
- текстовую информацию о модели и выкройке;
- ссылку на страницу изделия;
- сгенерированные теги.

Поддерживаемые сайты (seed):
- simplicity.com
- vikisews.com
- burdastyle.ru
- helpersew.com
- grasser.ru
- shkatulka-sew.ru
- korfiati.ru
- marfy.it

## Важно
- Скрипт **не скачивает саму выкройку** (PDF/DXF и т.п.), только изображения изделия и текстовую карточку.
- Фильтрация: женская/мужская одежда, без детского и аксессуаров.
- Можно остановить процесс (`Ctrl+C`), затем повторно запустить — прогресс восстановится из `state/`.

## Установка
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env`:
```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

## Запуск
```bash
python pattern_crawler.py --headless --max-items 50 --per-site-limit 25
```

## Структура результатов
```text
output/
  <item-slug-hash>/
    item.json
    image_01.jpg
    image_02.jpg
state/
  visited_urls.json
  downloaded_items.json
```

`item.json` содержит URL исходника, текстовые поля, сезонность/детали и `generated_tags`.
