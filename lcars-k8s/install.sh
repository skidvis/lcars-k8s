#!/usr/bin/env bash
# Install lcars-k8s into a private virtualenv and link it onto your PATH.
# Works on Ubuntu Server 22.04 and 24.04.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
VENV="$PREFIX/share/lcars-k8s"
BIN="$PREFIX/bin"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '\033[38;2;255;153;0m==>\033[0m %s\n' "$1"; }
die() { printf '\033[38;2;204;68;68m==> %s\033[0m\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 is not installed. Run: sudo apt install python3"

if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    die "Don't run this with sudo. It installs into your home directory, which you already own."
fi

# pip builds in place and needs to write an egg-info directory here. A tree
# unpacked with sudo is owned by root, so this fails in a confusing way later.
if [ ! -w "$SOURCE" ]; then
    printf '\033[38;2;204;68;68m==> %s is not writable by %s.\033[0m\n' "$SOURCE" "$(whoami)" >&2
    printf '    If you unpacked the tarball with sudo, take it back with:\n\n' >&2
    printf '      sudo chown -R %s:%s %s\n\n' "$(id -un)" "$(id -gn)" "$SOURCE" >&2
    exit 1
fi

python3 - <<'PY' || die "Python 3.10 or newer is required."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    say "Installing python3-venv (needs sudo)"
    sudo apt-get update -qq && sudo apt-get install -y python3-venv
fi

# setuptools cannot rewrite an egg-info directory left behind by an earlier
# run, so clear any build artifacts before starting.
if [ -d "$SOURCE/build" ] || compgen -G "$SOURCE"/*.egg-info >/dev/null; then
    say "Removing build artifacts from a previous run"
    rm -rf "$SOURCE"/build "$SOURCE"/*.egg-info
fi

if [ -d "$VENV" ]; then
    say "Replacing the existing virtualenv at $VENV"
    rm -rf "$VENV"
fi

say "Creating virtualenv at $VENV"
python3 -m venv "$VENV"

say "Installing lcars-k8s and its dependencies"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "$SOURCE"

mkdir -p "$BIN"
ln -sf "$VENV/bin/lcars-k8s" "$BIN/lcars-k8s"
say "Linked $BIN/lcars-k8s"

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "Add this to your ~/.bashrc:  export PATH=\"\$PATH:$BIN\"" ;;
esac

if ! command -v lcars-k8s >/dev/null 2>&1; then
    say "$BIN is not on this shell's PATH yet. For right now, run:"
    printf '\n      export PATH="%s:$PATH"\n' "$BIN"
    say "New logins pick it up automatically once ~/.local/bin exists."
fi

cat <<'EOF'

  Installed. Try it out:

    lcars-k8s --demo      preview against a synthetic cluster
    lcars-k8s             connect using your current kubeconfig
    lcars-k8s --help      all options

EOF
