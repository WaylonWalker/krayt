from krayt.templates import env
import typer
from typing import List, Optional

app = typer.Typer()


@app.command()
def list():
    typer.echo("Available templates:")
    for template in env.list_templates():
        typer.echo(template)


@app.command()
def base(
    volumes: Optional[List[str]] = typer.Option(
        None,
        "--volume",
    ),
    pvcs: Optional[List[str]] = typer.Option(
        None,
        "--pvc",
    ),
    additional_packages: Optional[List[str]] = typer.Option(
        None, "--additional-packages", "-ap"
    ),
    pre_init_scripts: Optional[List[str]] = typer.Option(
        None,
        "--pre-init-scripts",
        help="additional scripts to execute at the end of container initialization",
    ),
    post_init_scripts: Optional[List[str]] = typer.Option(
        None,
        "--post-init-scripts",
        "--init-scripts",
        help="additional scripts to execute at the start of container initialization",
    ),
    pre_init_hooks: Optional[List[str]] = typer.Option(
        None,
        "--pre-init-hooks",
        help="additional hooks to execute at the end of container initialization",
    ),
    post_init_hooks: Optional[List[str]] = typer.Option(
        None,
        "--post-init-hooks",
        "--init-hooks",
        help="additional hooks to execute at the start of container initialization",
    ),
):
    template_name = "base.sh"
    template = env.get_template(template_name)
    rendered = template.render(
        volumes=volumes,
        pvcs=pvcs,
        additional_packages=additional_packages,
        pre_init_scripts=pre_init_scripts,
        post_init_scripts=post_init_scripts,
        pre_init_hooks=pre_init_hooks,
        post_init_hooks=post_init_hooks,
    )
    print(rendered)


@app.command()
def install(
    additional_packages: Optional[List[str]] = typer.Option(
        ..., "--additional-packages", "-ap"
    ),
):
    template_name = "install.sh"
    template = env.get_template(template_name)
    rendered = template.render(additional_packages=additional_packages)
    print(rendered)


@app.command()
def motd(
    volumes: Optional[List[str]] = typer.Option(
        None,
        "--volume",
    ),
    pvcs: Optional[List[str]] = typer.Option(
        None,
        "--pvc",
    ),
    additional_packages: Optional[List[str]] = typer.Option(
        ..., "--additional-packages", "-ap"
    ),
):
    template_name = "motd.sh"
    template = env.get_template(template_name)
    rendered = template.render(
        volumes=volumes,
        pvcs=pvcs,
        additional_packages=additional_packages,
    )
    print(rendered)
