#!/bin/sh
echo "Setting up additional package repositories..."

# Add testing repository for newer packages
echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories

# Add community repository
echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories

# Update package list
apk update

# Install some useful tools from testing/community
apk add \
    @testing golang \
    @community rust \
    @community cargo

echo "Additional repositories configured and packages installed."
