# Krayt - The Kubernetes Volume Inspector

Like cracking open a Krayt dragon pearl, this tool helps you inspect what's inside your Kubernetes volumes.
Hunt down storage issues and explore your persistent data like a true Tatooine dragon hunter.

## Features

- 🔍 Create inspector pods with all the tools you need
- 📦 Access volumes and device mounts from any pod
- 🔎 Fuzzy search across all namespaces
- 🛠️ Built-in tools for file exploration and analysis
- 🧹 Automatic cleanup of inspector pods

## Installation

### Quick Install (Linux)

```bash
# Install latest version
curl -sSL https://github.com/waylonwalker/krayt/releases/latest/download/install.sh | sudo bash

# Install specific version
curl -sSL https://github.com/waylonwalker/krayt/releases/download/v0.1.0/install.sh | sudo bash
```

This will install the `krayt` command to `/usr/local/bin`.

### Manual Installation

1. Download the latest release for your platform from the [releases page](https://github.com/waylonwalker/krayt/releases)
2. Extract the archive: `tar xzf krayt-*.tar.gz`
3. Move the binary: `sudo mv krayt-*/krayt /usr/local/bin/krayt`
4. Make it executable: `sudo chmod +x /usr/local/bin/krayt`

## Usage

```bash
# Create a new inspector and apply it directly
krayt create | kubectl apply -f -

# Or review the manifest first
krayt create > inspector.yaml
kubectl apply -f inspector.yaml

# Connect to a running inspector
krayt exec

# Clean up inspectors
krayt clean

# Show version
krayt version
```

### Available Tools

Your inspector pod comes equipped with a full arsenal of tools:

- **File Navigation**: `lf`, `exa`, `fd`
- **Search & Analysis**: `ripgrep`, `bat`, `hexyl`
- **Disk Usage**: `ncdu`, `dust`
- **File Comparison**: `difftastic`
- **System Monitoring**: `bottom`, `htop`
- **JSON/YAML Tools**: `jq`, `yq`
- **Network Tools**: `mtr`, `dig`
- **Cloud & Database**: `aws-cli`, `sqlite3`

## Quotes from the Field

> "Inside every volume lies a pearl of wisdom waiting to be discovered."
> 
> -- Ancient Tatooine proverb

> "The path to understanding your storage is through exploration."
> 
> -- Krayt dragon hunter's manual

## May the Force be with your volumes!

Remember: A Krayt dragon's pearl is valuable not just for what it is, but for what it reveals about the dragon that created it. Similarly, your volumes tell a story about your application's data journey.
