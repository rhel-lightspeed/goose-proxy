#!/usr/bin/bash


# Red Hat specific customizations
GOOSE_REDHAT_DIR=${GOOSE_REDHAT_DIR:-"/usr/share/goose-redhat"}
GOOSE_REDHAT_CONFIG="${GOOSE_REDHAT_DIR}/config.yaml"
GOOSE_REDHAT_PROVIDER="${GOOSE_REDHAT_DIR}/rhel_cla.json"

# Goose specific folders
GOOSE_CONFIG_DIR="${HOME}/.config/goose"
GOOSE_CUSTOM_PROVIDER_DIR="${GOOSE_CONFIG_DIR}/custom_providers"

# Goose specifc config file and custom provider
GOOSE_CONFIG_FILE="${GOOSE_CONFIG_DIR}/config.yaml"
GOOSE_CUSTOM_PROVIDER_FILE="${GOOSE_CUSTOM_PROVIDER_DIR}/rhel_cla.json"

# Required provider/endpoint keys that must match the current backend.
# Only these keys are touched when migrating an existing config; all other
# user settings (extensions, model overrides, etc.) are left intact.
GOOSE_REQUIRED_KEYS=(
    "GOOSE_PROVIDER:rhel_cla"
    "OPENAI_BASE_PATH:v1/responses"
    "OPENAI_HOST:http://127.0.0.1:7080"
)

migrate_config_key() {
    local file="$1"
    local key="$2"
    local value="$3"

    if grep -q "^${key}:" "${file}"; then
        sed -i "s|^${key}:.*|${key}: ${value}|" "${file}"
    else
        echo "${key}: ${value}" >> "${file}"
    fi
}

needs_migration() {
    local file="$1"
    for entry in "${GOOSE_REQUIRED_KEYS[@]}"; do
        local key="${entry%%:*}"
        local value="${entry#*:}"
        local current
        current=$(grep "^${key}:" "${file}" 2>/dev/null)
        if [[ "${current}" != "${key}: ${value}" ]]; then
            return 0
        fi
    done
    return 1
}

mkdir -p "${GOOSE_CUSTOM_PROVIDER_DIR}"

# In case the custom provider does not exist, we will place ours in
# ~/.config/goose/custom_providers.
if [[ ! -f "${GOOSE_CUSTOM_PROVIDER_FILE}" ]]; then
    cp -pa "${GOOSE_REDHAT_PROVIDER}" "${GOOSE_CUSTOM_PROVIDER_FILE}"
fi

# In case the config file does not exist, we will place ours in the
# ~/.config/goose folder.
if [[ ! -f "${GOOSE_CONFIG_FILE}" ]]; then
    cp -pa "${GOOSE_REDHAT_CONFIG}" "${GOOSE_CONFIG_FILE}"
elif needs_migration "${GOOSE_CONFIG_FILE}"; then
    for entry in "${GOOSE_REQUIRED_KEYS[@]}"; do
        migrate_config_key "${GOOSE_CONFIG_FILE}" "${entry%%:*}" "${entry#*:}"
    done
    echo "[goose-init] Config updated: migrated provider/endpoint keys to current values." >&2
fi

unset GOOSE_REDHAT_DIR
unset GOOSE_REDHAT_CONFIG
unset GOOSE_REDHAT_PROVIDER

unset GOOSE_CONFIG_DIR
unset GOOSE_CONFIG_FILE

unset GOOSE_CUSTOM_PROVIDER_DIR
unset GOOSE_CUSTOM_PROVIDER_FILE
