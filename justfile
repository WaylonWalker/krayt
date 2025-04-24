delete-tag:
    #!/usr/bin/env bash
    set -euo pipefail
    
    # Get the version
    VERSION=$(hatch version)
    
    # Delete the tag
    git tag -d "v$VERSION"
    git push origin ":refs/tags/v$VERSION"

delete-release:
    #!/usr/bin/env bash
    set -euo pipefail
    
    # Get the version
    VERSION=$(hatch version)
    
    # Delete the release
    gh release delete "v$VERSION"

create-tag:
    #!/usr/bin/env bash
    VERSION=$(hatch version)
    git tag -a "v$VERSION" -m "Release v$VERSION"
    git push origin "v$VERSION"

create-archives:
    #!/usr/bin/env bash
    VERSION=$(hatch version)
    rm -rf dist build
    hatch build -t binary

    krayt_bin=dist/binary/krayt-${VERSION}/krayt_linux_amd64
    
    # Create the binary for each platform
    for platform in "x86_64-unknown-linux-gnu" "aarch64-unknown-linux-gnu"; do
        outbin="krayt-${VERSION}-${platform}"
        # Copy the Python script and update version
        cp ${krayt_bin} "dist/binary/${outbin}"
    done
    
    # Generate install.sh
    # ./scripts/generate_install_script.py "$VERSION"
    # chmod +x dist/install.sh

create-release: create-tag create-archives
    #!/usr/bin/env bash
    VERSION=$(hatch version)
    ./scripts/get_release_notes.py "$VERSION" > release_notes.tmp
    
    # Check if release already exists
    if gh release view "v$VERSION" &>/dev/null; then
        echo "Release v$VERSION already exists. Uploading binaries..."
        # Upload binaries to existing release
        gh release upload "v$VERSION" \
            dist/binary/krayt-${VERSION} \
            dist/binary/krayt-${VERSION}-aarch64-unknown-linux-gnu \
            dist/binary/krayt-${VERSION}-x86_64-unknown-linux-gnu || true
    else
        echo "Creating new release v$VERSION"
        # Create new release with binaries
        gh release create "v$VERSION" \
            --title "v$VERSION" \
            --notes-file release_notes.tmp \
            dist/binary/krayt-${VERSION} \
            dist/binary/krayt-${VERSION}-aarch64-unknown-linux-gnu \
            dist/binary/krayt-${VERSION}-x86_64-unknown-linux-gnu
    fi
    rm release_notes.tmp

preview-release-notes:
    #!/usr/bin/env bash
    VERSION=$(hatch version)
    ./scripts/get_release_notes.py "$VERSION" | less -R

release: create-release

