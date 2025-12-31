#!/usr/bin/env python3
"""Генерирует viewer.html из crafting_recipes.yaml и viewer_template.html"""

import yaml
import json
import sys
from pathlib import Path

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    # Читаем YAML
    print("Загрузка crafting_recipes.yaml...")
    yaml_file = Path('crafting_recipes.yaml')

    if not yaml_file.exists():
        print("Ошибка: crafting_recipes.yaml не найден!")
        print("Запустите сначала: python parse_crafting_recipes.py")
        return

    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Конвертируем в JSON
    print("Конвертация в JSON...")
    json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    # Читаем шаблон
    print("Загрузка viewer_template.html...")
    template_file = Path('viewer_template.html')

    if not template_file.exists():
        print("Ошибка: viewer_template.html не найден!")
        return

    template = template_file.read_text(encoding='utf-8')

    # Встраиваем данные
    print("Встраивание данных...")
    html = template.replace('/*DATA_PLACEHOLDER*/', f'const recipesData = {json_data};')

    # Сохраняем
    output_file = Path('viewer.html')
    output_file.write_text(html, encoding='utf-8')

    print(f"\n✓ Готово: {output_file}")
    print(f"  Размер: {len(html):,} байт")
    print(f"  Рецептов: {sum(len(level_data['recipes']) for station in data.values() for level_data in station.get('levels', {}).values())}")
    print(f"\nОткройте {output_file} в браузере для просмотра.")


if __name__ == '__main__':
    main()
