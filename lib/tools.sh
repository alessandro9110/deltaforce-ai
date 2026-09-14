# shellcheck shell=bash
#
# Project-local tool binaries (uv, Databricks CLI) and uv-managed Python.
# Versions are pinned in lib/data/versions.env.

df_download_and_extract() {
    local url=$1 dest=$2 archive
    archive="$dest/$(basename "$url")"
    mkdir -p "$dest"
    curl -fsSL --retry 3 -o "$archive" "$url" || df_die "Download failed: $url"
    case "$archive" in
        *.zip)    unzip -q -o "$archive" -d "$dest" ;;
        *.tar.gz) tar -xzf "$archive" -C "$dest" ;;
        *)        df_die "Unknown archive format: $archive" ;;
    esac
}

# df_install_binary NAME URL — extract NAME from the archive into .deltaforce/bin
df_install_binary() {
    local name=$1 url=$2 tmp found
    tmp="$DF_RUNTIME_DIR/tmp/$name"
    rm -rf "$tmp"
    df_download_and_extract "$url" "$tmp"
    found=$(find "$tmp" -type f -name "$name$DF_EXE" | head -n 1)
    [ -n "$found" ] || df_die "$name$DF_EXE not found in $url"
    mkdir -p "$DF_BIN_DIR"
    cp "$found" "$DF_BIN_DIR/$name$DF_EXE"
    chmod +x "$DF_BIN_DIR/$name$DF_EXE"
    rm -rf "$tmp"
}

df_install_uv() {
    if [ -x "$DF_UV" ]; then
        case "$("$DF_UV" --version 2>/dev/null)" in
            "uv $DF_UV_VERSION"|"uv $DF_UV_VERSION "*) df_ok "uv $DF_UV_VERSION"; return ;;
        esac
    fi
    local triple ext=tar.gz
    case "$DF_OS" in
        windows) triple="$DF_ARCH-pc-windows-msvc" ext=zip ;;
        linux)   triple="$DF_ARCH-unknown-linux-gnu" ;;
        darwin)  triple="$DF_ARCH-apple-darwin" ;;
    esac
    df_msg "Downloading uv $DF_UV_VERSION..."
    df_install_binary uv "https://github.com/astral-sh/uv/releases/download/$DF_UV_VERSION/uv-$triple.$ext"
    df_ok "uv $DF_UV_VERSION → $(df_rel "$DF_UV")"
}

df_install_databricks_cli() {
    local expected="Databricks CLI v$DF_DATABRICKS_CLI_VERSION"
    if [ -x "$DF_DATABRICKS" ] && [ "$("$DF_DATABRICKS" --version 2>/dev/null)" = "$expected" ]; then
        df_ok "$expected"
        return
    fi
    local arch=amd64 ext=tar.gz
    [ "$DF_ARCH" = aarch64 ] && arch=arm64
    [ "$DF_OS" = windows ] && ext=zip
    df_msg "Downloading Databricks CLI $DF_DATABRICKS_CLI_VERSION..."
    df_install_binary databricks \
        "https://github.com/databricks/cli/releases/download/v$DF_DATABRICKS_CLI_VERSION/databricks_cli_${DF_DATABRICKS_CLI_VERSION}_${DF_OS}_${arch}.$ext"
    df_ok "$expected → $(df_rel "$DF_DATABRICKS")"
}

df_install_tools() {
    df_install_uv
    df_install_databricks_cli
    "$DF_UV" python install --quiet "$DF_PYTHON_VERSION" || df_die "Could not install Python $DF_PYTHON_VERSION with uv"
    df_ok "Python $DF_PYTHON_VERSION (uv-managed, in $(df_rel "$DF_RUNTIME_DIR")/python)"
}
