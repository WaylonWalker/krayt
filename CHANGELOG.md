## 0.4.0

- create now has --apply to apply the generated manifest to the cluster
- generic templates endpoint for cli
- better motd for volume mounts

## 0.3.0

- created pypi release
- updated releases to use pyapp
- all new package
- port forward support
- additional_packages support

## 0.2.0

### Added

- Support for imagepullsecret flag on krayt create command
  - Allows pulling from private container registries by specifying an image pull secret

## 0.1.0

### Added

- Support for initialization scripts in `~/.config/krayt/init.d/`
  - Scripts run before package installation
  - Support for proxy configuration
  - Custom package repositories setup
  - Environment variable configuration
- Example initialization scripts:
  - `00_proxy.sh` for proxy configuration
  - `10_install_git.sh` for git installation and configuration
- Improved binary installation process
  - Better platform detection
  - Support for multiple archive formats (.tar.gz, .gz, .bz2, .zip, .bin)
  - Improved error handling and user feedback
  - Automatic sudo elevation when needed for binary installation

## 0.0.0

- Initial release
