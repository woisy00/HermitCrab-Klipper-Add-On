#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s <install|uninstall> <klipper-directory>\n' "$0" >&2
    printf '       %s config <printer-config-directory>\n' "$0" >&2
    exit 2
}

if (($# != 2)); then
    usage
fi

action=$1
klipper_directory=$2

case "$action" in
    install|uninstall|config)
        ;;
    *)
        usage
        ;;
esac

repository_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

if [[ "$action" == config ]]; then
    config_directory=$klipper_directory
    if [[ ! -f "${config_directory}/printer.cfg" ]]; then
        printf 'printer.cfg not found in: %s\n' "$config_directory" >&2
        exit 1
    fi
    config_directory="$(cd -- "$config_directory" && pwd -P)"
    hc_directory="${config_directory}/hc"
    mkdir -p -- "$hc_directory"

    macro_source="${repository_directory}/macros/hermitcrab.cfg"
    macro_destination="${hc_directory}/hermitcrab.cfg"
    if [[ -e "$macro_destination" || -L "$macro_destination" ]]; then
        printf 'Kept existing file: %s\n' "$macro_destination"
    else
        cp -- "$macro_source" "$macro_destination"
        printf 'Copied %s -> %s\n' "$macro_source" "$macro_destination"
    fi

    toolhead_file="${hc_directory}/toolheads.cfg"
    if [[ -e "$toolhead_file" || -L "$toolhead_file" ]]; then
        printf 'Kept existing file: %s\n' "$toolhead_file"
    else
        : > "$toolhead_file"
        printf 'Created %s\n' "$toolhead_file"
    fi

    # hc/hermitcrab.cfg includes toolheads.cfg; Klipper resolves it from hc/.
    hermitcrab_cfg="${hc_directory}/hermitcrab.cfg"
    toolhead_include='[include toolheads.cfg]'
    if grep -qxF -- "$toolhead_include" "$hermitcrab_cfg"; then
        printf 'Already included in %s: %s\n' "$hermitcrab_cfg" "$toolhead_include"
    else
        printf '\n%s\n' "$toolhead_include" >> "$hermitcrab_cfg"
        printf 'Added %s to %s\n' "$toolhead_include" "$hermitcrab_cfg"
    fi

    include_line='[include hc/hermitcrab.cfg]'
    printer_cfg="${config_directory}/printer.cfg"
    if grep -qxF -- "$include_line" "$printer_cfg"; then
        printf 'Already included in %s\n' "$printer_cfg"
    else
        # Insert before the SAVE_CONFIG block so Klipper's autosave stays at the end.
        tmp_cfg="$(mktemp)"
        awk -v line="$include_line" '
            !done && /^#\*# <-+ SAVE_CONFIG/ { print line; print ""; done = 1 }
            { print }
            END { if (!done) { print ""; print line } }
        ' "$printer_cfg" > "$tmp_cfg"
        cat -- "$tmp_cfg" > "$printer_cfg"
        rm -f -- "$tmp_cfg"
        printf 'Added %s to %s\n' "$include_line" "$printer_cfg"
    fi
    exit 0
fi

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
