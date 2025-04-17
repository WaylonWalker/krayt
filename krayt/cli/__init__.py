from krayt import __version__
from krayt.cli.bundles import app as bundles_app
from krayt.cli.pod import app as pod_app, create, exec, logs, clean
from krayt.cli.templates import app as templates_app
from typer import Typer

app = Typer()

app.add_typer(templates_app, name="templates", no_args_is_help=True)
app.add_typer(pod_app, name="pod", no_args_is_help=True)
app.command(name="create")(create)
app.command(name="c")(create)
app.command(name="clean")(clean)
app.command(name="exec")(exec)
app.command(name="logs")(logs)
app.add_typer(bundles_app, name="bundles", no_args_is_help=True)


@app.command()
def version():
    print(__version__)


def main():
    app()
