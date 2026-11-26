#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s <install|uninstall> <klipper-directory>\n' "$0" >&2
    exit 2
}

if (($# != 2)); then
    usage
fi

action=$1
klipper_directory=$2

case "$action" in
    install|uninstall)
        ;;
    *)
        usage
        ;;
esac

if [[ ! -d "$klipper_directory" ]]; then
    printf 'Klipper directory does not exist: %s\n' "$klipper_directory" >&2
    exit 1
fi

klipper_directory="$(cd -- "$klipper_directory" && pwd -P)"
klipper_extras="${klipper_directory}/klippy/extras"
if [[ ! -d "$klipper_extras" ]]; then
    printf 'Klipper extras directory does not exist: %s\n' "$klipper_extras" >&2
    exit 1
fi

repository_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
extension_extras="${repository_directory}/extras"
if [[ ! -d "$extension_extras" ]]; then
    printf 'Extension extras directory does not exist: %s\n' "$extension_extras" >&2
    exit 1
fi

shopt -s nullglob

if [[ "$action" == install ]]; then
    modules=("$extension_extras"/*.py)
    if ((${#modules[@]} == 0)); then
        printf 'No top-level Python modules found in %s\n' "$extension_extras" >&2
        exit 1
    fi

    for module in "${modules[@]}"; do
        destination="${klipper_extras}/$(basename -- "$module")"
        if [[ -L "$destination" && "$destination" -ef "$module" ]]; then
            continue
        fi
        if [[ -e "$destination" || -L "$destination" ]]; then
            printf 'Refusing to overwrite existing path: %s\n' "$destination" >&2
            exit 1
        fi
    done

    for module in "${modules[@]}"; do
        destination="${klipper_extras}/$(basename -- "$module")"
        if [[ -L "$destination" && "$destination" -ef "$module" ]]; then
            printf 'Already linked: %s\n' "$destination"
            continue
        fi

        ln -s "$module" "$destination"
        printf 'Linked %s -> %s\n' "$destination" "$module"
    done
else
    removed=0
    for destination in "$klipper_extras"/*; do
        if [[ -L "$destination" ]]; then
            target="$(readlink -- "$destination")"
            if [[ "$target" == "$extension_extras/"* ]]; then
                rm -- "$destination"
                printf 'Removed link: %s\n' "$destination"
                removed=1
            fi
        fi
    done

    if ((removed == 0)); then
        printf 'No extension links found in %s\n' "$klipper_extras"
    fi
fi
