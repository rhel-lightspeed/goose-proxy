#!/usr/bin/bash
	
	
# Red Hat specific customizations
GOOSE_REDHAT_DIR="/usr/share/goose-redhat"
GOOSE_REDHAT_CONFIG="${GOOSE_REDHAT_DIR}/config.yaml"
GOOSE_REDHAT_PROVIDER="${GOOSE_REDHAT_DIR}/custom_goose-proxy.json"
	
# Goose specific folders
GOOSE_CONFIG_DIR="${HOME}/.config/goose"
GOOSE_CUSTOM_PROVIDER_DIR="${GOOSE_CONFIG_DIR}/custom_providers"
	
# Goose specifc config file and custom provider
GOOSE_CONFIG_FILE="${GOOSE_CONFIG_DIR}/config.yaml"
GOOSE_CUSTOM_PROVIDER_FILE="${GOOSE_CUSTOM_PROVIDER_DIR}/custom_goose-proxy.json"
	
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
fi
	
unset GOOSE_REDHAT_DIR	
unset GOOSE_REDHAT_CONFIG
unset GOOSE_REDHAT_PROVIDER 
	
unset GOOSE_CONFIG_DIR
unset GOOSE_CONFIG_FILE
		
unset GOOSE_CUSTOM_PROVIDER_DIR
unset GOOSE_CUSTOM_PROVIDER_FILE