#!/usr/bin/env bash

set -euo pipefail

template_file="${1:-.env.example}"
output_file="${2:-.env}"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to generate ${output_file}" >&2
  exit 1
fi

if [[ -z "${GITHUB_VARS_JSON:-}" ]]; then
  GITHUB_VARS_JSON='{}'
fi

if [[ -z "${GITHUB_SECRETS_JSON:-}" ]]; then
  GITHUB_SECRETS_JSON='{}'
fi

missing_keys=()
tmp_file="$(mktemp)"

cleanup() {
  rm -f "${tmp_file}"
}

trap cleanup EXIT

while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
  line="${raw_line#"${raw_line%%[![:space:]]*}"}"

  if [[ -z "${line}" || "${line}" == \#* ]]; then
    continue
  fi

  key="${line%%=*}"
  key="${key%"${key##*[![:space:]]}"}"

  if [[ -z "${key}" ]]; then
    continue
  fi

  value="$(jq -r --arg key "${key}" '.[$key] // empty' <<<"${GITHUB_SECRETS_JSON}")"
  if [[ -z "${value}" ]]; then
    value="$(jq -r --arg key "${key}" '.[$key] // empty' <<<"${GITHUB_VARS_JSON}")"
  fi

  if [[ -z "${value}" ]]; then
    missing_keys+=("${key}")
    continue
  fi

  printf '%s=%s\n' "${key}" "${value}" >> "${tmp_file}"
done < "${template_file}"

if (( ${#missing_keys[@]} > 0 )); then
  printf 'Missing GitHub environment values for: %s\n' "${missing_keys[*]}" >&2
  exit 1
fi

mv "${tmp_file}" "${output_file}"
