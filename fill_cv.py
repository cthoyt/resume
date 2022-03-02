import os

import pystow
import yaml
from jinja2 import Environment, FileSystemLoader
from tabulate import tabulate

HERE = os.path.abspath(os.path.dirname(__file__))
DATA_BASE = 'https://raw.githubusercontent.com/cthoyt/cthoyt.github.io/master/_data'
PREFIX = 'cv'


def ensure_yaml(name: str, force: bool = True):
    path = pystow.ensure(PREFIX, url=f'{DATA_BASE}/{name}.yml', force=force)
    with path.open() as file:
        return yaml.safe_load(file)


def get_context():
    databases = ensure_yaml('databases')
    database_table_rows = []
    for database in databases:
        name, description = database['name'], database['description']
        if (logo_url := database.get('logo')) is not None:
            logo_name = None
            if logo_url.startswith('/'):  # local to repo
                logo_url = f'https://github.com/cthoyt/cthoyt.github.io/raw/master/{logo_url}'
            elif 'camo' in logo_url or 'avatars0' in logo_url or 'avatars1' in logo_url:
                logo_name = f'{name.lower()}.png'
            path = pystow.ensure(PREFIX, 'logos', url=logo_url, name=logo_name)
            graphics = f'\includegraphics[width=0.60cm]{{{path}}}'

            rtext = name
            if (github_name := database.get('github')) is not None:
                github_url = f'https://github.com/{github_name}'
                rtext += rf'\newline \includegraphics[scale=0.25]{{img/GitHub-Mark-32px.png}} \href{{{github_url}}}{{{github_name}}}'
            if (zenodo_id := database.get('zenodo')) is not None:
                zenodo_path = pystow.ensure(PREFIX, 'zenodo',
                                            url=f'https://zenodo.org/badge/doi/10.5281/zenodo.{zenodo_id}.svg')
                # rtext += rf'\includegraphics[scale=1]{zenodo_png_path}'
            database_table_rows.append((graphics, rtext))

    database_table_str = tabulate(database_table_rows, tablefmt='latex_raw')

    return dict(
        awards=ensure_yaml('awards'),
        database_table=database_table_str,
    )


def main():
    loader = FileSystemLoader(HERE)
    environment = Environment(
        autoescape=False,
        loader=loader,
        trim_blocks=False,
        variable_start_string='{$',
        variable_end_string='$}',
    )
    template = environment.get_template('cv_template.tex')
    path = os.path.join(HERE, 'cv.tex')
    with open(path, 'w') as file:
        print(template.render(get_context()), file=file)


if __name__ == '__main__':
    main()
