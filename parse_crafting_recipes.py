import yaml
import re
from bs4 import BeautifulSoup
from urllib.parse import unquote


def _convert_time_to_seconds(time_text):
    """Конвертирует текст времени в секунды."""
    hours = 0
    minutes = 0
    seconds = 0

    # Парсим часы
    h_match = re.search(r'(\d+)\s*ч', time_text)
    if h_match:
        hours = int(h_match.group(1))

    # Парсим минуты
    m_match = re.search(r'(\d+)\s*мин', time_text)
    if m_match:
        minutes = int(m_match.group(1))

    # Парсим секунды
    s_match = re.search(r'(\d+)\s*сек', time_text)
    if s_match:
        seconds = int(s_match.group(1))

    return hours * 3600 + minutes * 60 + seconds


def parse_duration_to_seconds(duration_text):
    """
    Парсит duration и конвертирует в секунды.
    Поддерживает форматы:
    - "1 ч 58 мин" → 7080
    - "56 мин 40 сек" → 3400
    - "от 40 ч 16 мин до 13 ч 20 мин 13 сек" → {min: 144960, max: 48013}
    """
    if not duration_text:
        return None

    # Проверяем диапазон
    if 'от' in duration_text and 'до' in duration_text:
        parts = duration_text.split('до')
        min_part = parts[0].replace('от', '').strip()
        max_part = parts[1].strip()
        return {
            'min': _convert_time_to_seconds(min_part),
            'max': _convert_time_to_seconds(max_part)
        }

    # Одиночное значение
    return _convert_time_to_seconds(duration_text)


def _parse_station_name_and_level(full_name):
    """
    Парсит полное имя станции и уровень.
    Examples:
    - "Верстак УР1" → ("Верстак", 1)
    - "Верстак УР 1" → ("Верстак", 1)
    - "Биткоин ферма" → ("Биткоин ферма", 1)
    """
    match = re.search(r'(.+?)\s+УР\s*(\d+)', full_name)
    if match:
        base_name = match.group(1).strip()
        level = int(match.group(2))
        return base_name, level
    return full_name, 1


def parse_recipes():
    with open('workbench/page.html', 'rb') as f:
        soup = BeautifulSoup(f, 'html.parser', from_encoding='utf-8')

    tables = soup.find_all('table', class_='wikitable mw-collapsible')

    stations = {}

    for table in tables:
        # Get station name from h3 (with level)
        h3 = table.find_previous('h3')
        if h3:
            full_name = h3.get_text(strip=True).replace('[]', '')
            base_name, level = _parse_station_name_and_level(full_name)
        else:
            # Fallback to h2
            h2 = table.find_previous('h2')
            if h2:
                base_name = h2.get_text(strip=True).replace('[]', '')
                level = 1
            else:
                base_name = "Unknown Station"
                level = 1

        # Initialize station structure
        if base_name not in stations:
            stations[base_name] = {
                'base_name': base_name,
                'wiki_link': None,
                'icon_link': None,
                'levels': {}
            }

        if level not in stations[base_name]['levels']:
            stations[base_name]['levels'][level] = {
                'recipes': []
            }

        rows = table.find_all('tr')[1:]  # Skip header row

        for row in rows:
            ths = row.find_all('th')
            if len(ths) != 5:
                continue

            input_th, arrow1, station_th, arrow2, output_th = ths

            # Get station wiki_link and icon_link from first row if not set yet
            if stations[base_name]['wiki_link'] is None or stations[base_name]['icon_link'] is None:
                center = station_th.find('center')
                if center:
                    # Get wiki_link
                    a_station = center.find('a', href=lambda x: x and x.startswith('/ru/wiki/'))
                    if a_station and stations[base_name]['wiki_link'] is None:
                        stations[base_name]['wiki_link'] = 'https://escapefromtarkov.fandom.com' + a_station['href']

                    # Get icon_link
                    if stations[base_name]['icon_link'] is None:
                        span_file = center.find('span', attrs={'typeof': 'mw:File/Frameless'})
                        if span_file:
                            a_icon = span_file.find('a', class_='mw-file-description')
                            if a_icon and a_icon.get('href'):
                                stations[base_name]['icon_link'] = a_icon['href']

            # Parse inputs
            inputs = []
            for p in input_th.find_all('p'):
                item = {}
                # Find a with wiki link
                a_wiki = None
                for a in p.find_all('a'):
                    if a.get('href', '').startswith('/ru/wiki/'):
                        a_wiki = a
                        break
                if a_wiki:
                    name = a_wiki.get('title') or a_wiki.get_text(strip=True)
                    if name:
                        item['name'] = name
                        item['wiki_link'] = 'https://escapefromtarkov.fandom.com' + a_wiki['href']
                        # Add icon_link from data-src
                        img = p.find('img')
                        if img and img.get('data-src'):
                            item['icon_link'] = img['data-src']
                code = p.find('code')
                if code:
                    qty_text = code.get_text(strip=True).replace('x', '').strip()
                    item['quantity'] = 0 if not qty_text else int(qty_text) if qty_text.isdigit() else 1
                    item['consumable'] = item['quantity'] != 0
                if item:
                    inputs.append(item)

            # Parse duration from station column
            duration = None
            b_tag = station_th.find('b')
            if b_tag:
                duration_text = b_tag.get_text(separator=' ', strip=True)
                duration = parse_duration_to_seconds(duration_text)

            # Parse output
            output = {}
            a_wiki = output_th.find('a', href=lambda x: x and x.startswith('/ru/wiki/'))
            if a_wiki:
                name = a_wiki.get('title') or a_wiki.get_text(strip=True)
                if name:
                    output['name'] = name
                    output['wiki_link'] = 'https://escapefromtarkov.fandom.com' + a_wiki['href']
                    # Add icon_link from data-src
                    img = output_th.find('img')
                    if img and img.get('data-src'):
                        output['icon_link'] = img['data-src']
            code = output_th.find('code')
            if code:
                qty = code.get_text(strip=True).replace('x', '').strip()
                output['quantity'] = int(qty) if qty.isdigit() else 1

            # Check for requirements
            requirements = []
            small = row.find('small') or row.find('span', class_='small')
            if small:
                # Check for electricity requirement
                generator_img = small.find('img', attrs={'data-src': lambda x: x and 'Generator_Portrait.png' in x})
                if not generator_img:
                    generator_img = small.find('img', alt=lambda x: x and 'генератор' in x.lower() if x else False)

                full_text = small.get_text(separator=' ', strip=True).lower()
                if generator_img or 'требуется в течение всего процесса' in full_text or 'необходимо на протяжении всего процесса' in full_text:
                    requirements.append({'type': 'electricity_required'})

                # Get all links and text
                links = small.find_all('a')
                text_parts = [s.strip() for s in small.stripped_strings]

                if links and text_parts:
                    req = {}
                    prefix = text_parts[0].lower()

                    # Determine requirement type
                    if 'во время прохождения' in prefix:
                        req['type'] = 'during_quest'
                        if links:
                            req['quest'] = links[0].get_text(strip=True)
                            req['quest_link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']
                    elif 'после принятия квеста' in prefix:
                        req['type'] = 'quest_accepted'
                        # Format: "После принятия квеста" + NPC_link + Quest_link
                        if len(links) >= 2:
                            req['npc'] = links[0].get_text(strip=True)
                            req['npc_link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']
                            req['quest'] = links[1].get_text(strip=True)
                            req['quest_link'] = 'https://escapefromtarkov.fandom.com' + links[1]['href']
                        elif len(links) == 1:
                            req['quest'] = links[0].get_text(strip=True)
                            req['quest_link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']
                    elif 'после выполнения квеста' in prefix:
                        req['type'] = 'quest_completed'
                        if links:
                            req['quest'] = links[0].get_text(strip=True)
                            req['quest_link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']
                    elif prefix.startswith('после'):
                        req['type'] = 'after_quest'
                        if links:
                            req['quest'] = links[0].get_text(strip=True)
                            req['quest_link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']
                    else:
                        # Generic requirement - только если это не electricity
                        if not (generator_img or 'требуется в течение всего процесса' in full_text):
                            req['type'] = 'other'
                            req['description'] = small.get_text(separator=' ', strip=True)
                            if links:
                                req['link'] = 'https://escapefromtarkov.fandom.com' + links[0]['href']

                    if req:
                        requirements.append(req)

            recipe = {
                'inputs': inputs,
                'output': output
            }
            if duration:
                recipe['duration'] = duration
            if requirements:
                recipe['requirements'] = requirements

            stations[base_name]['levels'][level]['recipes'].append(recipe)

    return stations

if __name__ == '__main__':
    stations = parse_recipes()
    with open('crafting_recipes.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(stations, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # Count total recipes across all stations and levels
    total_recipes = sum(
        len(level_data['recipes'])
        for station in stations.values()
        for level_data in station.get('levels', {}).values()
    )
    print(f"Parsed {total_recipes} recipes in {len(stations)} stations")

    # Debug: load YAML and print
    with open('crafting_recipes.yaml', 'r', encoding='utf-8') as f:
        loaded = yaml.safe_load(f)
    if loaded:
        first_station_name = list(loaded.keys())[0]
        first_station = loaded[first_station_name]
        print(f"\nFirst station: {first_station_name}")
        print(f"  base_name: {first_station.get('base_name')}")
        print(f"  wiki_link: {first_station.get('wiki_link')}")
        print(f"  icon_link: {first_station.get('icon_link')}")
        print(f"  levels: {list(first_station.get('levels', {}).keys())}")

        # Show first recipe from first level
        if first_station.get('levels'):
            first_level = list(first_station['levels'].keys())[0]
            first_level_data = first_station['levels'][first_level]
            print(f"  Level {first_level} recipes count: {len(first_level_data.get('recipes', []))}")

            if first_level_data.get('recipes'):
                first_recipe = first_level_data['recipes'][0]
                if first_recipe.get('inputs'):
                    print(f"  First recipe input: {first_recipe['inputs'][0].get('name')}")
                if first_recipe.get('duration'):
                    print(f"  Duration: {first_recipe['duration']}")
