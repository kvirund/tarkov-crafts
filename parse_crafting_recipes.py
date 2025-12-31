import yaml
from bs4 import BeautifulSoup
from urllib.parse import unquote

def parse_recipes():
    with open('workbench/page.html', 'rb') as f:
        soup = BeautifulSoup(f, 'html.parser', from_encoding='utf-8')

    tables = soup.find_all('table', class_='wikitable mw-collapsible')

    stations = {}

    for table in tables:
        # Get station name from table header
        header = table.find_previous('h3') or table.find_previous('h2') or table.find_previous('h4')
        if header:
            station_name = header.get_text(strip=True).replace('[]', '')
        else:
            station_name = "Unknown Station"

        if station_name not in stations:
            stations[station_name] = {
                'wiki_link': None,
                'recipes': []
            }

        rows = table.find_all('tr')[1:]  # Skip header row

        for row in rows:
            ths = row.find_all('th')
            if len(ths) != 5:
                continue

            input_th, arrow1, station_th, arrow2, output_th = ths

            # Get station wiki_link from first row if not set yet
            if stations[station_name]['wiki_link'] is None:
                center = station_th.find('center')
                if center:
                    a_station = center.find('a', href=lambda x: x and x.startswith('/ru/wiki/'))
                    if a_station:
                        stations[station_name]['wiki_link'] = 'https://escapefromtarkov.fandom.com' + a_station['href']

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
                duration = b_tag.get_text(separator=' ', strip=True)

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
                text = small.get_text(strip=True)
                a_req = small.find('a')
                if a_req and a_req.get('href'):
                    href = a_req['href']
                    link = 'https://escapefromtarkov.fandom.com' + href if href.startswith('/') else href
                    requirements.append(f"[{text}]({link})")
                else:
                    requirements.append(text)

            recipe = {
                'inputs': inputs,
                'output': output
            }
            if duration:
                recipe['duration'] = duration
            if requirements:
                recipe['requirements'] = requirements

            stations[station_name]['recipes'].append(recipe)

    return stations

if __name__ == '__main__':
    stations = parse_recipes()
    with open('crafting_recipes.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(stations, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    total_recipes = sum(len(station['recipes']) for station in stations.values())
    print(f"Parsed {total_recipes} recipes in {len(stations)} stations")

    # Debug: load YAML and print
    with open('crafting_recipes.yaml', 'r', encoding='utf-8') as f:
        loaded = yaml.safe_load(f)
    if loaded:
        first_station_name = list(loaded.keys())[0]
        first_station = loaded[first_station_name]
        print(f"First station: {repr(first_station_name)}")
        print(f"  wiki_link: {first_station.get('wiki_link')}")
        print(f"  recipes count: {len(first_station.get('recipes', []))}")
        if first_station.get('recipes'):
            first_recipe = first_station['recipes'][0]
            if first_recipe.get('inputs'):
                print(f"  First recipe input: {repr(first_recipe['inputs'][0].get('name'))}")
            if first_recipe.get('duration'):
                print(f"  Duration: {first_recipe['duration']}")
