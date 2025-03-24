#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "kubernetes",
#     "iterfzf"
# ]
# ///

from iterfzf import iterfzf
from kubernetes import client, config
import logging
import time
import typer
from typing import Any, Optional
import yaml
import os

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
            "persistentVolumeClaim": {
                "claimName": v.persistent_volume_claim.claim_name
            }
        }
    elif v.config_map:
        volume_source = {"configMap": {"name": v.config_map.name}}
    elif v.secret:
        volume_source = {"secret": {"secretName": v.secret.secret_name}}
    elif v.host_path:  # Add support for hostPath volumes (used for device mounts)
        volume_source = {
            "hostPath": {
                "path": v.host_path.path,
                "type": v.host_path.type if v.host_path.type else None
            }
        }
    elif v.empty_dir:  # Add support for emptyDir volumes (used for /dev/shm)
        volume_source = {
            "emptyDir": {
                "medium": v.empty_dir.medium if v.empty_dir.medium else None,
                "sizeLimit": v.empty_dir.size_limit if v.empty_dir.size_limit else None
            }
        }

    if not volume_source:
        return None

    return clean_dict({"name": v.name, **volume_source})


def fuzzy_select(items):
    """Use fzf to select from a list of (name, namespace) tuples"""
    if not items:
        return None, None

    # Format items as "namespace/name" for display
    formatted_items = [f"{ns}/{name}" for name, ns in items]
    logging.debug(f"Found {len(formatted_items)} pods")

    try:
        # Use iterfzf for selection
        selected = iterfzf(formatted_items)

        if selected:
            namespace, name = selected.split("/")
            logging.debug(f"Selected pod {name} in namespace {namespace}")
            return name, namespace
        else:
            logging.debug("No selection made")
            return None, None

    except Exception as e:
        logging.error(f"Error during selection: {e}", exc_info=True)
        typer.echo(f"Error during selection: {e}", err=True)
        raise typer.Exit(1)


def get_pods(namespace=None):
    """Get list of pods in the specified namespace or all namespaces"""
    config.load_kube_config()
    v1 = client.CoreV1Api()

    try:
        if namespace:
            logging.debug(f"Listing pods in namespace {namespace}")
            pod_list = v1.list_namespaced_pod(namespace=namespace)
        else:
            logging.debug("Listing pods in all namespaces")
            pod_list = v1.list_pod_for_all_namespaces()

        pods = [(pod.metadata.name, pod.metadata.namespace) for pod in pod_list.items]
        logging.debug(f"Found {len(pods)} pods")
        return pods
    except client.exceptions.ApiException as e:
        logging.error(f"Error listing pods: {e}")
        typer.echo(f"Error listing pods: {e}", err=True)
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
                volumes.append(client.V1Volume(
                    name=v.name,
                    empty_dir=client.V1EmptyDirVolumeSource(
                        medium="Memory"
                    )
                ))
            elif v.name in ["coral-device"]:
                volumes.append(client.V1Volume(
                    name=v.name,
                    host_path=client.V1HostPathVolumeSource(
                        path="/dev/apex_0",
                        type="CharDevice"
                    )
                ))
            elif v.name in ["qsv-device"]:
                volumes.append(client.V1Volume(
                    name=v.name,
                    host_path=client.V1HostPathVolumeSource(
                        path="/dev/dri",
                        type="Directory"
                    )
                ))
            else:
                volumes.append(v)

    # Filter out None values from volumes
    volumes = [v for v in volumes if format_volume(v)]
    
    return volume_mounts, volumes


def get_pod_env_and_secrets(api, namespace, pod_name):
    pod = api.read_namespaced_pod(pod_name, namespace)

    # Get environment variables from the pod
    env_vars = []
    for container in pod.spec.containers:
        if container.env:
            for env in container.env:
                env_dict = {"name": env.name}
                if env.value:
                    env_dict["value"] = env.value
                elif env.value_from:
                    if env.value_from.config_map_key_ref:
                        env_dict["valueFrom"] = {
                            "configMapKeyRef": {
                                "name": env.value_from.config_map_key_ref.name,
                                "key": env.value_from.config_map_key_ref.key,
                            }
                        }
                    elif env.value_from.secret_key_ref:
                        env_dict["valueFrom"] = {
                            "secretKeyRef": {
                                "name": env.value_from.secret_key_ref.name,
                                "key": env.value_from.secret_key_ref.key,
                            }
                        }
                    elif env.value_from.field_ref:
                        env_dict["valueFrom"] = {
                            "fieldRef": {
                                "fieldPath": env.value_from.field_ref.field_path
                            }
                        }
                env_vars.append(env_dict)

    # Get all volume mounts that are secrets
    secret_volumes = []
    if pod.spec.volumes:
        secret_volumes = [v for v in pod.spec.volumes if v.secret]

    return env_vars, secret_volumes


def create_inspector_job(api, namespace, pod_name, volume_mounts, volumes):
    timestamp = int(time.time())
    job_name = f"{pod_name}-inspector-{timestamp}"

    # Get environment variables and secrets from the target pod
    env_vars, secret_volumes = get_pod_env_and_secrets(api, namespace, pod_name)

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
        mount_info.append(f"{vm['name']}:{vm['mountPath']}")

    pvc_info = []
    for v in volumes:
        if hasattr(v, "persistent_volume_claim") and v.persistent_volume_claim:
            pvc_info.append(f"{v.name}:{v.persistent_volume_claim.claim_name}")

    inspector_job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {"app": "pvc-inspector"},
        },
        "spec": {
            "ttlSecondsAfterFinished": 0,  # Delete immediately after completion
            "template": {
                "metadata": {"labels": {"app": "pvc-inspector"}},
                "spec": {
                    "containers": [
                        {
                            "name": "inspector",
                            "image": "alpine:latest",  # Use Alpine as base for package management
                            "command": [
                                "sh",
                                "-c",
                                """
# Install basic tools first
apk update
apk add curl

# Install lf (terminal file manager)
curl -L https://github.com/gokcehan/lf/releases/download/r31/lf-linux-amd64.tar.gz | tar xzf - -C /usr/local/bin

# Install the rest of the tools
apk add ripgrep exa ncdu dust \
    file hexyl jq yq bat fd fzf \
    htop bottom difftastic \
    mtr bind-tools \
    aws-cli sqlite sqlite-dev sqlite-libs

# Function to update MOTD
update_motd() {
    cat << EOF > /etc/motd
====================================
PVC Inspector Pod
====================================
Mounted Volumes:
$(echo "$MOUNTS" | tr ',' '\\n' | sed 's/^/- /')

Persistent Volume Claims:
$(echo "$PVCS" | tr ',' '\\n' | sed 's/^/- /')

Mounted Secrets:
$(for d in /mnt/secrets/*; do if [ -d "$d" ]; then echo "- $(basename $d)"; fi; done)

Environment Variables:
$(env | sort | sed 's/^/- /')

Available Tools:
File Navigation:
- lf: Terminal file manager (run 'lf')
- exa: Modern ls (run 'ls', 'll', or 'tree')
- fd: Modern find (run 'fd pattern')

Search & Analysis:
- rg (ripgrep): Fast search (run 'rg pattern')
- bat: Better cat with syntax highlighting
- hexyl: Hex viewer (run 'hexyl file')
- file: File type detection

Disk Usage:
- ncdu: Interactive disk usage analyzer
- dust: Disk usage analyzer
- du: Standard disk usage tool

File Comparison:
- difft: Modern diff tool (alias 'diff')

System Monitoring:
- btm: Modern system monitor (alias 'top')
- htop: Interactive process viewer

JSON/YAML Tools:
- jq: JSON processor
- yq: YAML processor

Network Tools:
- dig: DNS lookup
- mtr: Network diagnostics

Cloud & Database:
- aws: AWS CLI
- sqlite3: SQLite database tool

Type 'tools-help' for detailed usage information
====================================
EOF
}

# Create helpful aliases and functions
cat << 'EOF' > /root/.ashrc
if [ "$PS1" ]; then
    cat /etc/motd
fi

# Aliases for better file navigation
alias ls='exa'
alias ll='exa -l'
alias la='exa -la'
alias tree='exa --tree'
alias find='fd'
alias top='btm'
alias diff='difft'
alias cat='bat --paging=never'

# Function to show detailed tool help
tools-help() {
    echo "PVC Inspector Tools Guide:"
    echo
    echo "File Navigation:"
    echo "  lf                   : Navigate with arrow keys, q to quit, h for help"
    echo "  ls, ll, la          : List files (exa with different options)"
    echo "  tree                : Show directory structure"
    echo "  fd pattern          : Find files matching pattern"
    echo
    echo "Search & Analysis:"
    echo "  rg pattern          : Search file contents"
    echo "  bat file            : View file with syntax highlighting"
    echo "  hexyl file          : View file in hex format"
    echo "  file path           : Determine file type"
    echo
    echo "Disk Usage:"
    echo "  ncdu                : Interactive disk usage analyzer (navigate with arrows)"
    echo "  dust path           : Tree-based disk usage"
    echo "  du -sh *            : Summarize disk usage"
    echo
    echo "File Comparison:"
    echo "  diff file1 file2    : Compare files with syntax highlighting"
    echo
    echo "System Monitoring:"
    echo "  top (btm)           : Modern system monitor"
    echo "  htop                : Process viewer"
    echo
    echo "JSON/YAML Tools:"
    echo "  jq . file.json      : Format and query JSON"
    echo "  yq . file.yaml      : Format and query YAML"
    echo
    echo "Network Tools:"
    echo "  dig domain          : DNS lookup"
    echo "  mtr host            : Network diagnostics"
    echo
    echo "Cloud & Database:"
    echo "  aws                 : AWS CLI tool"
    echo "  sqlite3             : SQLite database tool"
    echo
    echo "Secrets:"
    echo "  ls /mnt/secrets     : List mounted secrets"
}

# Set some helpful environment variables
export EDITOR=vi
export PAGER=less
EOF

# Set up environment to always source our RC file
echo "export ENV=/root/.ashrc" > /etc/profile
echo "export ENV=/root/.ashrc" > /etc/environment

# Make RC file available to all shells
cp /root/.ashrc /etc/profile.d/motd.sh
ln -sf /root/.ashrc /root/.profile
ln -sf /root/.ashrc /root/.bashrc
ln -sf /root/.ashrc /root/.mkshrc
ln -sf /root/.ashrc /etc/shinit

# Create initial MOTD
update_motd

sleep 3600
                                """,
                            ],
                            "env": env_vars
                            + [
                                {"name": "MOUNTS", "value": ",".join(mount_info)},
                                {"name": "PVCS", "value": ",".join(pvc_info)},
                                {"name": "ENV", "value": "/root/.ashrc"},
                            ],
                            "volumeMounts": formatted_mounts,
                        }
                    ],
                    "volumes": [format_volume(v) for v in volumes if format_volume(v)],
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

@app.command()
def exec_inspector(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
):
    """
    Execute a shell in a running inspector pod. If multiple inspectors are found,
    presents a fuzzy finder to select one.
    """
    config.load_kube_config()
    batch_api = client.BatchV1Api()

    try:
        if namespace:
            logging.debug(f"Listing jobs in namespace {namespace}")
            jobs = batch_api.list_namespaced_job(
                namespace=namespace, label_selector="app=pvc-inspector"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(
                label_selector="app=pvc-inspector"
            )

        running_inspectors = []
        for job in jobs.items:
            # Get the pod for this job
            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(
                namespace=job.metadata.namespace,
                label_selector=f"job-name={job.metadata.name}"
            )
            for pod in pods.items:
                if pod.status.phase == "Running":
                    running_inspectors.append((pod.metadata.name, pod.metadata.namespace))

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

        # Execute the shell
        typer.echo(f"Connecting to inspector {pod_namespace}/{pod_name}...")
        os.execvp("kubectl", ["kubectl", "exec", "-it", "-n", pod_namespace, pod_name, "--", "sh", "-l"])

    except client.exceptions.ApiException as e:
        logging.error(f"Failed to list jobs: {e}")
        typer.echo(f"Failed to list jobs: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def cleanup_inspectors(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will cleanup in all namespaces.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Skip confirmation prompt.",
    ),
):
    """
    Delete all PVC inspector jobs in the specified namespace or all namespaces
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
                namespace=namespace, label_selector="app=pvc-inspector"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(
                label_selector="app=pvc-inspector"
            )

        # Filter out jobs in protected namespaces
        jobs.items = [job for job in jobs.items if job.metadata.namespace not in PROTECTED_NAMESPACES]

        if not jobs.items:
            typer.echo("No PVC inspector jobs found.")
            return

        # Show confirmation prompt
        if not yes:
            job_list = "\n".join(f"  {job.metadata.namespace}/{job.metadata.name}" for job in jobs.items)
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
def create_inspector(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for pods across all namespaces.",
    ),
):
    """
    Create a PVC inspector job. If namespace is not specified, will search for pods across all namespaces.
    The inspector job will be created in the same namespace as the selected pod.
    """
    pods = get_pods(namespace)
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
        client.CoreV1Api(), selected_namespace, selected_pod, volume_mounts, volumes
    )

    # Output the job manifest
    typer.echo(yaml.dump(clean_dict(inspector_job), sort_keys=False))


if __name__ == "__main__":
    app()
