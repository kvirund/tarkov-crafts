#!/usr/bin/env python3
"""Анализ производственных циклов Escape from Tarkov"""

import yaml
import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


class CraftingGraph:
    """Граф крафтов для поиска циклов"""

    def __init__(self, recipes_data):
        self.recipes = []  # List of all recipes
        self.item_to_producers = defaultdict(list)  # item_name -> [recipe_ids]
        self.item_to_consumers = defaultdict(list)  # item_name -> [recipe_ids]
        self.recipe_id_map = {}  # recipe_id -> recipe object

        self._build_graph(recipes_data)

    def _build_graph(self, recipes_data):
        """Построение графа из YAML данных"""
        recipe_id = 0

        for station_name, station in recipes_data.items():
            for level, level_data in station.get('levels', {}).items():
                for recipe in level_data.get('recipes', []):
                    recipe_obj = {
                        'id': recipe_id,
                        'station': station_name,
                        'level': level,
                        'inputs': recipe['inputs'],
                        'output': recipe['output'],
                        'duration': recipe.get('duration', 0),
                        'requirements': recipe.get('requirements', [])
                    }

                    self.recipes.append(recipe_obj)
                    self.recipe_id_map[recipe_id] = recipe_obj

                    # Индекс: что производит
                    output_name = recipe['output']['name']
                    self.item_to_producers[output_name].append(recipe_id)

                    # Индекс: что потребляет (игнорируем инструменты)
                    for input_item in recipe['inputs']:
                        if not input_item.get('consumable', True):
                            continue  # Пропускаем инструменты

                        input_name = input_item['name']
                        self.item_to_consumers[input_name].append(recipe_id)

                    recipe_id += 1

    def find_all_cycles(self, max_length=10, min_length=2):
        """Находит все циклы длиной от min_length до max_length"""
        cycles = []
        visited_in_path = set()

        def dfs(recipe_id, path):
            if recipe_id in path:
                # Найден цикл!
                cycle_start_idx = path.index(recipe_id)
                cycle = path[cycle_start_idx:]

                # Проверка длины
                if len(cycle) < min_length:
                    return

                # Нормализуем (начинаем с минимального ID)
                min_idx = cycle.index(min(cycle))
                normalized = tuple(cycle[min_idx:] + cycle[:min_idx])

                if normalized not in cycles:
                    cycles.append(normalized)
                return

            if recipe_id in visited_in_path or len(path) >= max_length:
                return

            visited_in_path.add(recipe_id)
            path.append(recipe_id)

            # Получаем рецепты, потребляющие output текущего рецепта
            recipe = self.recipe_id_map[recipe_id]
            output_name = recipe['output']['name']

            for next_recipe_id in self.item_to_consumers.get(output_name, []):
                dfs(next_recipe_id, path[:])  # Копируем путь

            visited_in_path.remove(recipe_id)

        # Запускаем DFS от каждого рецепта
        for recipe_id in range(len(self.recipes)):
            visited_in_path.clear()
            dfs(recipe_id, [])

        return cycles

    def print_cycle_analysis(self, analysis, cycle_num):
        """Вывод анализа цикла в консоль"""
        print(f"\n{'='*80}")
        print(f"ЦИКЛ #{cycle_num}")
        print(f"{'='*80}")

        print(f"\nПуть ({len(analysis.cycle)} рецептов):")
        for i, recipe_id in enumerate(analysis.cycle, 1):
            recipe = self.recipe_id_map[recipe_id]
            print(f"  {i}. [{recipe['station']} УР{recipe['level']}] → {recipe['output']['name']}")

        print(f"\nВремя: {format_duration(analysis.total_duration)}")

        print(f"\nПОТРЕБЛЯЕТ:")
        for item, qty in sorted(analysis.inputs_consumed.items()):
            print(f"  - {item}: {qty}")

        print(f"\nПРОИЗВОДИТ:")
        for item, qty in sorted(analysis.outputs_produced.items()):
            print(f"  + {item}: {qty}")

        print(f"\nБАЛАНС:")
        for item, balance in sorted(analysis.net_balance.items(), key=lambda x: -x[1]):
            sign = '+' if balance > 0 else ''
            print(f"  {sign}{balance} {item}")

        if analysis.is_self_sustaining:
            print(f"\n✓ САМОВОСПРОИЗВОДЯЩИЙСЯ")
        else:
            print(f"\n✗ Требует внешние ресурсы")

    def export_to_json(self, analyses, filename='cycle_analysis.json'):
        """Экспорт результатов в JSON"""
        data = {
            'total_cycles': len(analyses),
            'self_sustaining_count': sum(1 for a in analyses if a.is_self_sustaining),
            'cycles': []
        }

        for i, analysis in enumerate(analyses):
            cycle_data = {
                'id': i + 1,
                'path': [
                    {
                        'recipe_id': rid,
                        'station': self.recipe_id_map[rid]['station'],
                        'level': self.recipe_id_map[rid]['level'],
                        'output': self.recipe_id_map[rid]['output']['name']
                    }
                    for rid in analysis.cycle
                ],
                'duration_seconds': analysis.total_duration,
                'inputs': analysis.inputs_consumed,
                'outputs': analysis.outputs_produced,
                'balance': analysis.net_balance,
                'self_sustaining': analysis.is_self_sustaining
            }
            data['cycles'].append(cycle_data)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class CycleAnalysis:
    """Анализ одного цикла"""

    def __init__(self, cycle, graph, config=None):
        self.cycle = cycle  # Tuple[recipe_id]
        self.graph = graph
        self.config = config or {}
        self.recipes = [graph.recipe_id_map[rid] for rid in cycle]

        self.total_duration = self._calculate_duration()
        self.inputs_consumed = self._calculate_inputs()
        self.outputs_produced = self._calculate_outputs()
        self.net_balance = self._calculate_balance()
        self.is_self_sustaining = self._check_self_sustaining()

    def _calculate_duration(self):
        """Общее время цикла"""
        mode = self.config.get('duration_mode', 'range')

        if mode == 'range':
            # Возвращаем {min: X, max: Y} для диапазонов
            total_min = 0
            total_max = 0
            has_range = False

            for recipe in self.recipes:
                duration = recipe['duration']
                if isinstance(duration, dict):
                    total_min += duration['min']
                    total_max += duration['max']
                    has_range = True
                else:
                    total_min += duration
                    total_max += duration

            return {'min': total_min, 'max': total_max} if has_range else total_min

        elif mode == 'avg':
            # Среднее для диапазонов
            total = 0
            for recipe in self.recipes:
                duration = recipe['duration']
                if isinstance(duration, dict):
                    total += (duration['min'] + duration['max']) / 2
                else:
                    total += duration
            return total

        elif mode in ('min', 'max'):
            # Минимум или максимум для диапазонов
            total = 0
            for recipe in self.recipes:
                duration = recipe['duration']
                if isinstance(duration, dict):
                    total += duration[mode]
                else:
                    total += duration
            return total

        return 0

    def _calculate_inputs(self):
        """Все потребляемые предметы"""
        inputs = defaultdict(int)
        for recipe in self.recipes:
            for item in recipe['inputs']:
                if not item.get('consumable', True):
                    continue

                name = item['name']
                qty = item['quantity']
                inputs[name] += qty
        return dict(inputs)

    def _calculate_outputs(self):
        """Все производимые предметы"""
        outputs = defaultdict(int)
        for recipe in self.recipes:
            output = recipe['output']
            name = output['name']
            qty = output['quantity']
            outputs[name] += qty
        return dict(outputs)

    def _calculate_balance(self):
        """Чистый баланс (выход - вход)"""
        all_items = set(self.inputs_consumed.keys()) | set(self.outputs_produced.keys())
        balance = {}

        for item in all_items:
            consumed = self.inputs_consumed.get(item, 0)
            produced = self.outputs_produced.get(item, 0)
            net = produced - consumed

            if net != 0:
                balance[item] = net

        return balance

    def _check_self_sustaining(self):
        """
        Самовоспроизводящийся цикл:
        1. Все входы производятся внутри (баланс >= 0)
        2. Есть хотя бы один предмет с профитом (баланс > 0)
        """
        has_profit = False

        for item, balance in self.net_balance.items():
            if balance < 0:
                return False  # Нужны внешние ресурсы
            if balance > 0:
                has_profit = True

        return has_profit


class AnalysisConfig:
    """Конфигурация параметров анализа"""

    def __init__(self):
        # Поиск циклов
        self.max_cycle_length = 10
        self.min_cycle_length = 1

        # Расчет duration
        self.duration_mode = 'range'  # 'min', 'max', 'avg', 'range'

        # Фильтры
        self.include_non_sustaining = True
        self.min_profit_items = 0

        # Вывод
        self.output_format = 'both'  # 'console', 'json', 'both'
        self.sort_by = 'self_sustaining'  # 'self_sustaining', 'length', 'duration'

    @classmethod
    def from_args(cls):
        """Создать конфигурацию из аргументов командной строки"""
        parser = argparse.ArgumentParser(
            description='Анализ производственных циклов Escape from Tarkov'
        )

        parser.add_argument('--max-length', type=int, default=10,
                          help='Максимальная длина цикла (default: 10)')
        parser.add_argument('--min-length', type=int, default=1,
                          help='Минимальная длина цикла (default: 1)')
        parser.add_argument('--duration-mode', choices=['min', 'max', 'avg', 'range'],
                          default='range',
                          help='Режим расчета duration для диапазонов (default: range)')
        parser.add_argument('--only-sustaining', action='store_true',
                          help='Показывать только самовоспроизводящиеся циклы')
        parser.add_argument('--output', choices=['console', 'json', 'both'],
                          default='both',
                          help='Формат вывода (default: both)')
        parser.add_argument('--sort', choices=['self_sustaining', 'length', 'duration'],
                          default='self_sustaining',
                          help='Сортировка результатов (default: self_sustaining)')

        args = parser.parse_args()

        config = cls()
        config.max_cycle_length = args.max_length
        config.min_cycle_length = args.min_length
        config.duration_mode = args.duration_mode
        config.include_non_sustaining = not args.only_sustaining
        config.output_format = args.output
        config.sort_by = args.sort

        return config


def format_duration(duration):
    """Форматирование duration"""
    if isinstance(duration, dict):
        return f"{format_seconds(duration['min'])} - {format_seconds(duration['max'])}"
    return format_seconds(duration)


def format_seconds(seconds):
    """Конвертация секунд в читаемый формат"""
    if not seconds:
        return '0сек'

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f'{hours}ч')
    if minutes > 0:
        parts.append(f'{minutes}мин')
    if secs > 0:
        parts.append(f'{secs}сек')

    return ' '.join(parts) if parts else '0сек'


def get_duration_value(duration):
    """Получить числовое значение duration (для сортировки)"""
    if isinstance(duration, dict):
        return (duration['min'] + duration['max']) / 2
    return duration


def main():
    # Конфигурация
    config = AnalysisConfig.from_args()

    # Загрузка
    print("Загрузка crafting_recipes.yaml...")
    yaml_file = Path('crafting_recipes.yaml')

    if not yaml_file.exists():
        print("Ошибка: crafting_recipes.yaml не найден!")
        print("Запустите сначала: python parse_crafting_recipes.py")
        return

    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Построение графа
    print("Построение графа...")
    graph = CraftingGraph(data)
    print(f"  Рецептов: {len(graph.recipes)}")
    print(f"  Уникальных предметов: {len(set(graph.item_to_producers.keys()) | set(graph.item_to_consumers.keys()))}")

    # Поиск циклов
    print(f"Поиск циклов (длина {config.min_cycle_length}-{config.max_cycle_length})...")
    cycles = graph.find_all_cycles(
        max_length=config.max_cycle_length,
        min_length=config.min_cycle_length
    )
    print(f"  Найдено циклов: {len(cycles)}")

    if not cycles:
        print("Циклов не обнаружено!")
        return

    # Анализ
    print("Анализ циклов...")
    analyses = [CycleAnalysis(cycle, graph, vars(config)) for cycle in cycles]

    # Фильтрация
    if not config.include_non_sustaining:
        analyses = [a for a in analyses if a.is_self_sustaining]
        print(f"  После фильтрации: {len(analyses)} самовоспроизводящихся")

    if not analyses:
        print("После фильтрации циклов не осталось!")
        return

    # Сортировка
    if config.sort_by == 'self_sustaining':
        analyses.sort(key=lambda a: (-a.is_self_sustaining, -len(a.cycle)))
    elif config.sort_by == 'length':
        analyses.sort(key=lambda a: -len(a.cycle))
    elif config.sort_by == 'duration':
        analyses.sort(key=lambda a: -get_duration_value(a.total_duration))

    # Вывод
    if config.output_format in ('console', 'both'):
        print("\n" + "="*80)
        print("РЕЗУЛЬТАТЫ АНАЛИЗА")
        print("="*80)

        for i, analysis in enumerate(analyses, 1):
            graph.print_cycle_analysis(analysis, i)

    # Экспорт
    if config.output_format in ('json', 'both'):
        print("\nЭкспорт в JSON...")
        graph.export_to_json(analyses, 'cycle_analysis.json')
        print("  Сохранено: cycle_analysis.json")

    # Статистика
    self_sustaining = [a for a in analyses if a.is_self_sustaining]
    print(f"\nИтого:")
    print(f"  Всего циклов: {len(analyses)}")
    print(f"  Самовоспроизводящихся: {len(self_sustaining)}")
    print(f"  С внешними ресурсами: {len(analyses) - len(self_sustaining)}")


if __name__ == '__main__':
    main()
