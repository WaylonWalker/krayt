#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "typer",
#     "kubernetes",
#     "iterfzf"
# ]
# ///
"""
Krayt - The Kubernetes Volume Inspector

Like cracking open a Krayt dragon pearl, this tool helps you inspect what's inside your Kubernetes volumes.
Hunt down storage issues and explore your persistent data like a true Tatooine dragon hunter.

May the Force be with your volumes!
"""

from iterfzf import iterfzf
from kubernetes import client, config
import logging
import os
from pathlib import Path
import time
import typer
from typing import Any, Optional
import yaml

KRAYT_VERSION = "NIGHTLY"

logging.basicConfig(level=logging.WARNING)

app = typer.Typer()


def clean_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Remove None values and empty dicts from a dictionary recursively."""
    if not isinstance(d, dict):
        return d
    return {
        k: clean_dict(v)
        for k, v in d.items()
        if v is not None and v != {} and not (isinstance(v, dict) and not clean_dict(v))
    }


def format_volume_mount(vm: client.V1VolumeMount) -> dict[str, Any]:
    """Format volume mount with only relevant fields."""
    # Skip Kubernetes service account mounts
    if vm.mount_path.startswith("/var/run/secrets/kubernetes.io/"):
        return None

    return clean_dict(
        {
            "name": vm.name,
            "mountPath": vm.mount_path,
            "readOnly": vm.read_only if vm.read_only else None,
        }
    )


def format_volume(v: client.V1Volume) -> dict[str, Any]:
    """Format volume into a dictionary, return None if it should be skipped"""
    # Skip Kubernetes service account volumes
    if v.name.startswith("kube-api-access-"):
        return None

    volume_source = None
    if v.persistent_volume_claim:
        volume_source = {
            "persistentVolumeClaim": {"claimName": v.persistent_volume_claim.claim_name}
        }
    elif v.config_map:
        volume_source = {"configMap": {"name": v.config_map.name}}
    elif v.secret:
        volume_source = {"secret": {"secretName": v.secret.secret_name}}
    elif v.host_path:  # Add support for hostPath volumes (used for device mounts)
        volume_source = {
            "hostPath": {
                "path": v.host_path.path,
                "type": v.host_path.type if v.host_path.type else None,
            }
        }
    elif v.empty_dir:  # Add support for emptyDir volumes (used for /dev/shm)
        volume_source = {
            "emptyDir": {
                "medium": v.empty_dir.medium if v.empty_dir.medium else None,
                "sizeLimit": v.empty_dir.size_limit if v.empty_dir.size_limit else None,
            }
        }

    if not volume_source:
        return None

    return clean_dict({"name": v.name, **volume_source})


def fuzzy_select(items):
    """Use fzf to select from a list of (name, namespace) tuples"""
    if not items:
        return None, None

    # If there's only one item, return it without prompting
    if len(items) == 1:
        return items[0]

    # Format items for display
    formatted_items = [f"{name} ({namespace})" for name, namespace in items]

    # Use fzf for selection
    try:
        selected = iterfzf(formatted_items)
        if not selected:
            return None, None

        # Parse selection back into name and namespace
        # Example: "pod-name (namespace)" -> ("pod-name", "namespace")
        name = selected.split(" (")[0]
        namespace = selected.split(" (")[1][:-1]
        return name, namespace

    except Exception as e:
        typer.echo(f"Error during selection: {e}")
        return None, None


def get_pods(
    namespace=None,
    label_selector: str = "app=krayt",
):
    """Get list of pods in the specified namespace or all namespaces"""
    try:
        config.load_kube_config()
        api = client.CoreV1Api()
        if namespace:
            pods = api.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
            )
        else:
            pods = api.list_pod_for_all_namespaces(
                label_selector=label_selector,
            )

        # Convert to list of (name, namespace) tuples
        pod_list = []
        for pod in pods.items:
            if pod.metadata.namespace not in PROTECTED_NAMESPACES:
                pod_list.append((pod.metadata.name, pod.metadata.namespace))
        return pod_list

    except client.rest.ApiException as e:
        typer.echo(f"Error listing pods: {e}")
        raise typer.Exit(1)


def get_pod_spec(pod_name, namespace):
    config.load_kube_config()
    v1 = client.CoreV1Api()
    return v1.read_namespaced_pod(pod_name, namespace)


def get_pod_volumes_and_mounts(pod_spec):
    """Extract all volumes and mounts from a pod spec"""
    volume_mounts = []
    for container in pod_spec.spec.containers:
        if container.volume_mounts:
            volume_mounts.extend(container.volume_mounts)

    # Filter out None values from volume mounts
    volume_mounts = [vm for vm in volume_mounts if format_volume_mount(vm)]

    # Get all volumes, including device mounts
    volumes = []
    if pod_spec.spec.volumes:
        for v in pod_spec.spec.volumes:
            # Handle device mounts
            if v.name in ["cache-volume"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        empty_dir=client.V1EmptyDirVolumeSource(medium="Memory"),
                    )
                )
            elif v.name in ["coral-device"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        host_path=client.V1HostPathVolumeSource(
                            path="/dev/apex_0", type="CharDevice"
                        ),
                    )
                )
            elif v.name in ["qsv-device"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        host_path=client.V1HostPathVolumeSource(
                            path="/dev/dri", type="Directory"
                        ),
                    )
                )
            else:
                volumes.append(v)

    # Filter out None values from volumes
    volumes = [v for v in volumes if format_volume(v)]

    return volume_mounts, volumes


def get_env_vars_and_secret_volumes(api, namespace: str):
    """Get environment variables and secret volumes for the inspector pod"""
    env_vars = []
    volumes = []

    # Add proxy environment variables if they exist in the host environment
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]

    for var in proxy_vars:
        if var in os.environ:
            env_vars.append({"name": var, "value": os.environ[var]})

    # Look for secret volumes in the namespace
    try:
        secrets = api.list_namespaced_secret(namespace)
        for secret in secrets.items:
            # Skip service account tokens and other system secrets
            if secret.type != "Opaque" or secret.metadata.name.startswith(
                "default-token-"
            ):
                continue

            # Mount each secret as a volume
            volume_name = f"secret-{secret.metadata.name}"
            volumes.append(
                client.V1Volume(
                    name=volume_name,
                    secret=client.V1SecretVolumeSource(
                        secret_name=secret.metadata.name
                    ),
                )
            )

    except client.exceptions.ApiException as e:
        if e.status != 404:  # Ignore if no secrets found
            logging.warning(f"Failed to list secrets in namespace {namespace}: {e}")

    return env_vars, volumes


def get_init_scripts():
    """Get the contents of init scripts to be run in the pod"""
    init_dir = Path.home() / ".config" / "krayt" / "init.d"
    if not init_dir.exists():
        logging.debug("No init.d directory found at %s", init_dir)
        return ""

    scripts = sorted(init_dir.glob("*.sh"))
    if not scripts:
        logging.debug("No init scripts found in %s", init_dir)
        return ""

    # Create a combined script that will run all init scripts
    init_script = "#!/bin/bash\n\n"
    init_script += "exec 2>&1  # Redirect stderr to stdout for proper logging\n"
    init_script += "set -e     # Exit on error\n\n"
    init_script += "echo 'Running initialization scripts...' | tee /tmp/init.log\n\n"
    init_script += "mkdir -p /tmp/init.d\n\n"  # Create directory once at the start

    for script in scripts:
        try:
            with open(script, "r") as f:
                script_content = f.read()
                if not script_content.strip():
                    logging.debug("Skipping empty script %s", script)
                    continue

                # Use a unique heredoc delimiter for each script to avoid nesting issues
                delimiter = f"EOF_SCRIPT_{script.stem.upper()}"
                
                init_script += f"echo '=== Running {script.name} ===' | tee -a /tmp/init.log\n"
                init_script += f"cat > /tmp/init.d/{script.name} << '{delimiter}'\n"
                init_script += script_content
                if not script_content.endswith("\n"):
                    init_script += "\n"
                init_script += f"{delimiter}\n"
                init_script += f"chmod +x /tmp/init.d/{script.name}\n"
                init_script += f"cd /tmp/init.d && ./{script.name} 2>&1 | tee -a /tmp/init.log || {{ echo \"Failed to run {script.name}\"; exit 1; }}\n"
                init_script += f"echo '=== Finished {script.name} ===' | tee -a /tmp/init.log\n\n"
        except Exception as e:
            logging.error(f"Failed to load init script {script}: {e}")

    init_script += "echo 'Initialization scripts complete.' | tee -a /tmp/init.log\n"
    return init_script


def get_motd_script(mount_info, pvc_info):
    """Generate the MOTD script with proper escaping"""
    return f"""
# Create MOTD
cat << EOF > /etc/motd
====================================
Krayt Dragon's Lair
A safe haven for volume inspection
====================================

"Inside every volume lies a pearl of wisdom waiting to be discovered."

Mounted Volumes:
$(echo "{",".join(mount_info)}" | tr ',' '\\n' | sed 's/^/- /')

Persistent Volume Claims:
$(echo "{",".join(pvc_info)}" | tr ',' '\\n' | sed 's/^/- /')

Mounted Secrets:
$(for d in /mnt/secrets/*; do if [ -d "$d" ]; then echo "- $(basename $d)"; fi; done)

Init Script Status:
$(if [ -f /tmp/init.log ]; then echo "View initialization log at /tmp/init.log"; fi)
EOF
"""


def create_inspector_job(
    api,
    namespace: str,
    pod_name: str,
    volume_mounts: list,
    volumes: list,
    image: str = "alpine:latest",
    imagepullsecret: Optional[str] = None,
):
    """Create a Krayt inspector job with the given mounts"""
    timestamp = int(time.time())
    job_name = f"{pod_name}-krayt-{timestamp}"

    # Get environment variables and secret volumes from the target pod
    env_vars, secret_volumes = get_env_vars_and_secret_volumes(api, namespace)

    # Add secret volumes to our volumes list
    volumes.extend(secret_volumes)

    # Create corresponding volume mounts for secrets
    secret_mounts = []
    for vol in secret_volumes:
        secret_mounts.append(
            {
                "name": vol.name,
                "mountPath": f"/mnt/secrets/{vol.secret.secret_name}",
                "readOnly": True,
            }
        )

    # Convert volume mounts to dictionaries
    formatted_mounts = [format_volume_mount(vm) for vm in volume_mounts]
    formatted_mounts.extend(secret_mounts)

    # Format mount and PVC info for MOTD
    mount_info = []
    for vm in formatted_mounts:
        if vm:
            mount_info.append(f"{vm['name']}:{vm['mountPath']}")

    pvc_info = []
    for v in volumes:
        if hasattr(v, "persistent_volume_claim") and v.persistent_volume_claim:
            pvc_info.append(f"{v.name}:{v.persistent_volume_claim.claim_name}")

    init_scripts = get_init_scripts()

    # Build the command script
    command_parts = []

    # Configure apk proxy settings BEFORE any package installation
    command_parts.extend(
        [
            "# Configure apk proxy settings",
            "mkdir -p /etc/apk",
            "cat > /etc/apk/repositories << 'EOF'",
            "https://dl-cdn.alpinelinux.org/alpine/latest-stable/main",
            "https://dl-cdn.alpinelinux.org/alpine/latest-stable/community",
            "EOF",
            "",
            'if [ ! -z "$HTTP_PROXY" ]; then',
            '  echo "Setting up apk proxy configuration..."',
            "  mkdir -p /etc/apk/",
            "  cat > /etc/apk/repositories << EOF",
            "#/media/cdrom/apks",
            "http://dl-cdn.alpinelinux.org/alpine/latest-stable/main",
            "http://dl-cdn.alpinelinux.org/alpine/latest-stable/community",
            "",
            "# Configure proxy",
            "proxy=$HTTP_PROXY",
            "EOF",
            "fi",
            "",
            "# Install basic tools first",
            "apk update",
            "apk add curl",
            "",
            "# Install uv CLI",
            "echo 'Installing uv CLI...'",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "echo 'uv version:'",
            "uv --version",
            "",
            "echo 'Installing starship...'",
            "curl -sS https://starship.rs/install.sh | sh -s -- -y",
            "echo 'starship version:'",
            "starship --version",
            "",
            "",
            "# Install additional tools",
            "apk add "
            + " ".join(
                [
                    "ripgrep",
                    "exa",
                    "ncdu",
                    "dust",
                    "file",
                    "hexyl",
                    "jq",
                    "yq",
                    "bat",
                    "fd",
                    "fzf",
                    "htop",
                    "bottom",
                    "difftastic",
                    "mtr",
                    "bind-tools",
                    "aws-cli",
                    "sqlite",
                    "sqlite-dev",
                    "sqlite-libs",
                    "bash",
                    "neovim",
                ]
            ),
            "",
        ]
    )

    # Add init scripts if present
    if init_scripts:
        command_parts.extend(
            [
                "# Set up init script environment",
                "mkdir -p /tmp/init.d",
                "",
                "# Write and run init scripts",
                "cat > /tmp/init.sh << 'EOFSCRIPT'",
                init_scripts,
                "EOFSCRIPT",
                "",
                "# Make init script executable and run it",
                "chmod +x /tmp/init.sh",
                "bash /tmp/init.sh",
                "",
            ]
        )

    # Add shell setup and MOTD
    command_parts.extend(
        [
            "# Create .ashrc with MOTD",
            "cat > /root/.ashrc << 'EOF'",
            "# Display MOTD on login",
            "[ -f /etc/motd ] && cat /etc/motd",
            "# Set up shell environment",
            "export EDITOR=vi",
            "export PAGER=less",
            "# Set up aliases",
            "alias ll='ls -la'",
            "alias l='ls -la'",
            "alias la='ls -la'",
            "alias vi='vim'",
            "# Set up PATH",
            "export PATH=/root/.local/bin:$PATH",
            'eval "$(starship init bash)"',
            "EOF",
            "",
            "",
            "# Set up environment to always source our RC file",
            "echo 'export ENV=/root/.ashrc' > /etc/profile",
            "echo 'export ENV=/root/.ashrc' > /etc/environment",
            "",
            "# Make RC file available to all shells",
            "mkdir -p /etc/profile.d",
            "cp /root/.ashrc /etc/profile.d/motd.sh",
            "ln -sf /root/.ashrc /root/.profile",
            "ln -sf /root/.ashrc /root/.bashrc",
            "ln -sf /root/.ashrc /root/.mkshrc",
            "ln -sf /root/.ashrc /etc/shinit",
            "",
            "# Update MOTD",
            get_motd_script(mount_info, pvc_info),
            "",
            "# Keep container running",
            "tail -f /dev/null",
        ]
    )

    inspector_job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {"app": "krayt"},
            "annotations": {"pvcs": ",".join(pvc_info) if pvc_info else "none"},
        },
        "spec": {
            "template": {
                "metadata": {"labels": {"app": "krayt"}},
                "spec": {
                    "containers": [
                        {
                            "name": "inspector",
                            "image": image,
                            "command": ["sh", "-c", "\n".join(command_parts)],
                            "env": env_vars,
                            "volumeMounts": formatted_mounts,
                        }
                    ],
                    "volumes": [format_volume(v) for v in volumes if format_volume(v)],
                    "imagePullSecrets": [{"name": imagepullsecret}] if imagepullsecret else None,
                    "restartPolicy": "Never",
                },
            },
        },
    }
    return inspector_job


PROTECTED_NAMESPACES = {
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "argo-events",
    "argo-rollouts",
    "argo-workflows",
    "argocd",
    "cert-manager",
    "ingress-nginx",
    "monitoring",
    "prometheus",
    "istio-system",
    "linkerd",
}


def load_init_scripts():
    """Load and execute initialization scripts from ~/.config/krayt/scripts/"""
    init_dir = Path.home() / ".config" / "krayt" / "scripts"
    if not init_dir.exists():
        return

    # Sort scripts to ensure consistent execution order
    scripts = sorted(init_dir.glob("*.py"))

    for script in scripts:
        try:
            with open(script, "r") as f:
                exec(f.read(), globals())
            logging.debug(f"Loaded init script: {script}")
        except Exception as e:
            logging.error(f"Failed to load init script {script}: {e}")


def setup_environment():
    """Set up the environment with proxy settings and other configurations"""
    # Load environment variables for proxies
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]

    for var in proxy_vars:
        if var in os.environ:
            # Make both upper and lower case versions available
            os.environ[var.upper()] = os.environ[var]
            os.environ[var.lower()] = os.environ[var]


def version_callback(value: bool):
    if value:
        typer.echo(f"Version: {KRAYT_VERSION}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version", callback=version_callback
    ),
):
    """
    Krack open a Krayt dragon!
    """
    if ctx.invoked_subcommand is None:
        ctx.get_help()


@app.command()
def exec(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
):
    """
    Enter the Krayt dragon's lair! Connect to a running inspector pod.
    If multiple inspectors are found, you'll get to choose which one to explore.
    """
    config.load_kube_config()
    batch_api = client.BatchV1Api()

    try:
        if namespace:
            logging.debug(f"Listing jobs in namespace {namespace}")
            jobs = batch_api.list_namespaced_job(
                namespace=namespace, label_selector="app=krayt"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(label_selector="app=krayt")

        running_inspectors = []
        for job in jobs.items:
            # Get the pod for this job
            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(
                namespace=job.metadata.namespace,
                label_selector=f"job-name={job.metadata.name}",
            )
            for pod in pods.items:
                if pod.status.phase == "Running":
                    running_inspectors.append(
                        (pod.metadata.name, pod.metadata.namespace)
                    )

        if not running_inspectors:
            typer.echo("No running inspector pods found.")
            raise typer.Exit(1)

        if len(running_inspectors) == 1:
            pod_name, pod_namespace = running_inspectors[0]
        else:
            pod_name, pod_namespace = fuzzy_select(running_inspectors)
            if not pod_name:
                typer.echo("No inspector selected.")
                raise typer.Exit(1)

        exec_command = [
            "kubectl",
            "exec",
            "-it",
            "-n",
            pod_namespace,
            pod_name,
            "--",
            "/bin/bash",
            "-l",
        ]

        os.execvp("kubectl", exec_command)

    except client.exceptions.ApiException as e:
        logging.error(f"Failed to list jobs: {e}")
        typer.echo(f"Failed to list jobs: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def clean(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will cleanup in all namespaces.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
):
    """
    Clean up after your hunt! Remove all Krayt inspector jobs.
    Use --yes/-y to skip confirmation and clean up immediately.
    """
    config.load_kube_config()
    batch_api = client.BatchV1Api()

    try:
        if namespace:
            if namespace in PROTECTED_NAMESPACES:
                typer.echo(f"Error: Cannot cleanup in protected namespace {namespace}")
                raise typer.Exit(1)
            logging.debug(f"Listing jobs in namespace {namespace}")
            jobs = batch_api.list_namespaced_job(
                namespace=namespace, label_selector="app=krayt"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(label_selector="app=krayt")

        # Filter out jobs in protected namespaces
        jobs.items = [
            job
            for job in jobs.items
            if job.metadata.namespace not in PROTECTED_NAMESPACES
        ]

        if not jobs.items:
            typer.echo("No Krayt inspector jobs found.")
            return

        # Show confirmation prompt
        if not yes:
            job_list = "\n".join(
                f"  {job.metadata.namespace}/{job.metadata.name}" for job in jobs.items
            )
            typer.echo(f"The following inspector jobs will be deleted:\n{job_list}")
            if not typer.confirm("Are you sure you want to continue?"):
                typer.echo("Operation cancelled.")
                return

        # Delete each job
        for job in jobs.items:
            try:
                logging.debug(
                    f"Deleting job {job.metadata.namespace}/{job.metadata.name}"
                )
                batch_api.delete_namespaced_job(
                    name=job.metadata.name,
                    namespace=job.metadata.namespace,
                    body=client.V1DeleteOptions(propagation_policy="Background"),
                )
                typer.echo(f"Deleted job: {job.metadata.namespace}/{job.metadata.name}")
            except client.exceptions.ApiException as e:
                logging.error(
                    f"Failed to delete job {job.metadata.namespace}/{job.metadata.name}: {e}"
                )
                typer.echo(
                    f"Failed to delete job {job.metadata.namespace}/{job.metadata.name}: {e}",
                    err=True,
                )

    except client.exceptions.ApiException as e:
        logging.error(f"Failed to list jobs: {e}")
        typer.echo(f"Failed to list jobs: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def create(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for pods across all namespaces.",
    ),
    image: str = typer.Option(
        "alpine:latest",
        "--image",
        "-i",
        help="Container image to use for the inspector pod",
    ),
    imagepullsecret: Optional[str] = typer.Option(
        None,
        "--imagepullsecret",
        help="Name of the image pull secret to use for pulling private images",
    ),
):
    """
    Krack open a Krayt dragon! Create an inspector pod to explore what's inside your volumes.
    If namespace is not specified, will search for pods across all namespaces.
    The inspector will be created in the same namespace as the selected pod.
    """
    # For create, we want to list all pods, not just Krayt pods
    pods = get_pods(namespace, label_selector=None)
    if not pods:
        typer.echo("No pods found.")
        raise typer.Exit(1)

    selected_pod, selected_namespace = fuzzy_select(pods)
    if not selected_pod:
        typer.echo("No pod selected.")
        raise typer.Exit(1)

    pod_spec = get_pod_spec(selected_pod, selected_namespace)
    volume_mounts, volumes = get_pod_volumes_and_mounts(pod_spec)

    inspector_job = create_inspector_job(
        client.CoreV1Api(),
        selected_namespace,
        selected_pod,
        volume_mounts,
        volumes,
        image=image,
        imagepullsecret=imagepullsecret,
    )

    # Output the job manifest
    typer.echo(yaml.dump(clean_dict(inspector_job), sort_keys=False))


@app.command()
def version():
    """Show the version of Krayt."""
    typer.echo(f"Version: {KRAYT_VERSION}")


@app.command()
def logs(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow the logs in real-time",
    ),
):
    """
    View logs from a Krayt inspector pod.
    If multiple inspectors are found, you'll get to choose which one to explore.
    """
    pods = get_pods(namespace)
    if not pods:
        typer.echo("No pods found.")
        raise typer.Exit(1)

    selected_pod, selected_namespace = fuzzy_select(pods)
    if not selected_pod:
        typer.echo("No pod selected.")
        raise typer.Exit(1)

    try:
        config.load_kube_config()
        api = client.CoreV1Api()
        logs = api.read_namespaced_pod_log(
            name=selected_pod,
            namespace=selected_namespace,
            follow=follow,
            _preload_content=False,
        )

        if follow:
            for line in logs:
                typer.echo(line.decode("utf-8").strip())
        else:
            typer.echo(logs.read().decode("utf-8"))

    except client.rest.ApiException as e:
        typer.echo(f"Error reading logs: {e}")
        raise typer.Exit(1)


def main():
    setup_environment()
    load_init_scripts()
    app()


if __name__ == "__main__":
    main()
