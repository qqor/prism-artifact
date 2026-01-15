from pathlib import Path

import click

from scripts.eval.functions import make_crete_environments_cache


@click.command()
@click.argument("project_name", type=str)
@click.argument("challenge_project_directory", type=str)
@click.argument("cache_directory", type=str)
def make_crete_environments_cache_command(
    project_name: str, challenge_project_directory: str, cache_directory: str
):
    make_crete_environments_cache(
        project_name, Path(challenge_project_directory), Path(cache_directory)
    )


if __name__ == "__main__":
    make_crete_environments_cache_command()
