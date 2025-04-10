from krayt import bundles
import typer

app = typer.Typer()


@app.command()
def list(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
):
    """List available bundles"""
    typer.echo("Available bundles:")
    # get all variables from bundles
    for bundle in bundles.__dict__.keys():
        if bundle.startswith("__"):
            continue
        typer.echo(bundle)
        if verbose:
            for package in bundles.__dict__[bundle]:
                typer.echo(f"  - {package}")
