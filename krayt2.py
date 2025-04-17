#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "kubernetes",
#     "InquirerPy",
# ]
# ///

from InquirerPy import inquirer
from kubernetes import client, config
import os
import typer
from typing import List, Optional

app = typer.Typer(name="krayt")

VERSION = "0.1.0"

# Default values
container_image_default = "ubuntu:22.04"
container_name_default = "krayt-container"

KNOWN_PACKAGE_MANAGERS = {
    "apk": "apk add",
    "dnf": "dnf install -y",
    "yum": "yum install -y",
    "apt-get": "apt-get update && apt-get install -y",
    "apt": "apt update && apt install -y",
    "zypper": "zypper install -y",
    "pacman": "pacman -Sy --noconfirm",
}


def load_kube_config():
    try:
        config.load_kube_config()
    except Exception as e:
        typer.secho(f"Failed to load kubeconfig: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


def detect_package_manager_command() -> str:
    checks = [
        f"which {pm} >/dev/null 2>&1 && echo {cmd}"
        for pm, cmd in KNOWN_PACKAGE_MANAGERS.items()
    ]
    return " || ".join(checks)


def get_proxy_env_vars() -> List[client.V1EnvVar]:
    proxy_vars = [
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    ]
    env_vars = []
    for var in proxy_vars:
        value = os.environ.get(var)
        if value:
            env_vars.append(client.V1EnvVar(name=var, value=value))
    return env_vars


def fuzzy_pick_pod(namespace: Optional[str] = None) -> str:
    load_kube_config()
    core_v1 = client.CoreV1Api()
    if namespace is None:
        pods = core_v1.list_pod_for_all_namespaces()
    else:
        pods = core_v1.list_namespaced_pod(namespace=namespace)
    pods = {pod.metadata.name: pod for pod in pods.items}
    if not pods:
        typer.secho("No pods found to clone.", fg=typer.colors.RED)
        raise typer.Exit(1)
    choice = inquirer.fuzzy(
        message="Select a pod to clone:", choices=pods.keys()
    ).execute()
    return pods[choice]


def clone_pod(core_v1, namespace: str, source_pod_name: str):
    source_pod = core_v1.read_namespaced_pod(name=source_pod_name, namespace=namespace)
    container = source_pod.spec.containers[0]
    breakpoint()
    return (
        container.image,
        container.volume_mounts,
        source_pod.spec.volumes,
        container.env,
        source_pod.spec.image_pull_secrets,
    )


@app.command()
def create(
    image: str = typer.Option(
        container_image_default, "--image", "-i", help="Image to use for the container"
    ),
    name: str = typer.Option(
        container_name_default, "--name", "-n", help="Name for the krayt container"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-Y", help="Non-interactive, pull images without asking"
    ),
    fuzzy_clone: bool = typer.Option(
        False,
        "--fuzzy-clone",
        "-f",
        help="Clone an existing pod",
    ),
    clone: Optional[str] = typer.Option(
        None, "--clone", "-c", help="Clone an existing krayt container"
    ),
    volume: List[str] = typer.Option(
        [],
        "--volume",
        help="Additional volumes to add to the container (pvc-name:/mount/path)",
    ),
    additional_flags: List[str] = typer.Option(
        [],
        "--additional-flags",
        "-a",
        help="Additional flags to pass to the container manager command",
    ),
    additional_packages: List[str] = typer.Option(
        [],
        "--additional-packages",
        "-ap",
        help="Additional packages to install during setup",
    ),
    init_hooks: List[str] = typer.Option(
        [], "--init-hooks", help="Commands to execute at the end of initialization"
    ),
    pre_init_hooks: List[str] = typer.Option(
        [],
        "--pre-init-hooks",
        help="Commands to execute at the start of initialization",
    ),
    namespace: str = typer.Option(None, help="Kubernetes namespace"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Only print the generated Kubernetes manifest"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show more verbosity"),
    image_pull_secret: Optional[str] = typer.Option(
        None,
        "--image-pull-secret",
        help="Name of the Kubernetes secret for pulling the image",
    ),
):
    """Create a new Kubernetes pod inspired by distrobox."""
    load_kube_config()
    core_v1 = client.CoreV1Api()

    if fuzzy_clone:
        namespace, clone = fuzzy_pick_pod(namespace)

    if clone is not None:
        image, volume_mounts, volumes, env_vars, image_pull_secrets = clone_pod(
            core_v1, namespace, clone
        )
    else:
        volume_mounts = []
        volumes = []
        env_vars = get_proxy_env_vars()
        for idx, pvc_entry in enumerate(volume):
            try:
                pvc_name, mount_path = pvc_entry.split(":", 1)
            except ValueError:
                typer.secho(
                    f"Invalid volume format: {pvc_entry}. Use pvc-name:/mount/path",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(1)

            volumes.append(
                client.V1Volume(
                    name=f"volume-{idx}",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    ),
                )
            )
            volume_mounts.append(
                client.V1VolumeMount(
                    name=f"volume-{idx}",
                    mount_path=mount_path,
                )
            )

    package_manager_detection = detect_package_manager_command()
    package_manager_detection = """
detect_package_manager_and_install_command() {
    if [ $# -eq 0 ]; then
        echo "Usage: detect_package_manager_and_install_command <package1> [package2] [...]"
        return 1
    fi

    if command -v apt >/dev/null 2>&1; then
        PKG_MANAGER="apt"
        UPDATE_CMD="apt update &&"
        INSTALL_CMD="apt install -y"
    elif command -v dnf >/dev/null 2>&1; then
        PKG_MANAGER="dnf"
        UPDATE_CMD=""
        INSTALL_CMD="dnf install -y"
    elif command -v yum >/dev/null 2>&1; then
        PKG_MANAGER="yum"
        UPDATE_CMD=""
        INSTALL_CMD="yum install -y"
    elif command -v pacman >/dev/null 2>&1; then
        PKG_MANAGER="pacman"
        UPDATE_CMD=""
        INSTALL_CMD="pacman -Sy --noconfirm"
    elif command -v zypper >/dev/null 2>&1; then
        PKG_MANAGER="zypper"
        UPDATE_CMD=""
        INSTALL_CMD="zypper install -y"
    elif command -v apk >/dev/null 2>&1; then
        PKG_MANAGER="apk"
        UPDATE_CMD=""
        INSTALL_CMD="apk add"
    else
        echo "No supported package manager found."
        return 2
    fi

    PACKAGES="$*"

    if [ -n "$UPDATE_CMD" ]; then
        echo "$UPDATE_CMD
        echo $INSTALL_CMD $PACKAGES"
        $UPDATE_CMD
        $INSTALL_CMD $PACKAGES

    else
        echo "$INSTALL_CMD $PACKAGES"
        $INSTALL_CMD $PACKAGES
    fi
}
"""

    pre_hooks_command = " && ".join(pre_init_hooks) if pre_init_hooks else ""
    install_packages_command = ""
    if additional_packages:
        install_packages_command = f"{package_manager_detection}\n detect_package_manager_and_install_command {' '.join(additional_packages)}"
        # install_packages_command = (
        #     f"$({{package_manager_detection}} {' '.join(additional_packages)})"
        # )
    post_hooks_command = " && ".join(init_hooks) if init_hooks else ""

    combined_command_parts = [
        cmd
        for cmd in [pre_hooks_command, install_packages_command, post_hooks_command]
        if cmd
    ]
    command = None

    if combined_command_parts:
        combined_command = " && ".join(combined_command_parts)
        command = ["/bin/sh", "-c", f"{combined_command} && tail -f /dev/null"]

    pod_spec = client.V1PodSpec(
        containers=[
            client.V1Container(
                name=name,
                image=image,
                command=command,
                volume_mounts=volume_mounts if volume_mounts else None,
                env=env_vars if env_vars else None,
            )
        ],
        volumes=volumes if volumes else None,
        restart_policy="Never",
    )

    if image_pull_secret:
        pod_spec.image_pull_secrets = [
            client.V1LocalObjectReference(name=image_pull_secret)
        ]
    elif clone and image_pull_secrets:
        pod_spec.image_pull_secrets = image_pull_secrets

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace), spec=pod_spec
    )

    if dry_run or verbose:
        typer.secho(f"Dry-run/Verbose: Pod definition:\n{pod}", fg=typer.colors.BLUE)

    if dry_run:
        typer.secho("Dry run completed.", fg=typer.colors.GREEN)
        raise typer.Exit()

    typer.secho(
        f"Creating pod '{name}' in namespace '{namespace}'...", fg=typer.colors.GREEN
    )
    core_v1.create_namespaced_pod(namespace=namespace, body=pod)
    typer.secho("Pod created successfully.", fg=typer.colors.GREEN)


@app.command("fuzzy-pick-pod")
def cli_fuzzy_pick_pod(
    namespace: str = typer.Option(None, help="Kubernetes namespace"),
):
    load_kube_config()
    pod = fuzzy_pick_pod(namespace)

    if not pod:
        typer.secho("No pod selected.", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.secho("Selected pod", fg=typer.colors.GREEN)
    typer.secho(f"Name: {pod.metadata.name}", fg=typer.colors.GREEN)
    typer.secho(f"Namespace: {pod.metadata.namespace}", fg=typer.colors.GREEN)
    typer.secho(f"Image: {pod.spec.containers[0].image}", fg=typer.colors.GREEN)
    typer.secho(f"Command: {pod.spec.containers[0].command}", fg=typer.colors.GREEN)
    typer.secho(f"Volume mounts: {pod.spec.volumes}", fg=typer.colors.GREEN)
    typer.secho(
        f"Environment variables: {pod.spec.containers[0].env}", fg=typer.colors.GREEN
    )

    return pod


@app.command()
def version(show: bool = typer.Option(False, "--version", "-V", help="Show version")):
    if show:
        typer.echo(f"krayt version {VERSION}")


if __name__ == "__main__":
    app()
