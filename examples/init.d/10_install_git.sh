#!/bin/sh
echo "Installing additional development tools..."

# Install git and related tools
apk add git git-lfs

# Configure git defaults
git config --global init.defaultBranch main
git config --global core.editor vi
git config --global pull.rebase false

# Add some helpful git aliases
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.unstage 'reset HEAD --'
git config --global alias.last 'log -1 HEAD'

echo "Git configuration complete."
