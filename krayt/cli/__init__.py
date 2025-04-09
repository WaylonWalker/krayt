from krayt import __version__
from krayt.cli.create import app as create_app
from krayt.cli.templates import app as templates_app
from typer import Typer

app = Typer()

app.add_typer(templates_app, name="templates")
app.add_typer(create_app, name="create")


@app.command()
def version():
    print(__version__)


def main():
    app()
