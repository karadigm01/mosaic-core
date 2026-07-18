#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LLAMA_DIR="${REPO_ROOT}/models/llama.cpp"
SERVER_BIN="${LLAMA_DIR}/build/bin/llama-server"
MODEL_PATH="${REPO_ROOT}/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
HOST="${LLAMA_SERVER_HOST:-127.0.0.1}"
PORT="${LLAMA_SERVER_PORT:-8088}"
THREADS="${LLAMA_SERVER_THREADS:-$(nproc)}"
CONTEXT="${LLAMA_SERVER_CTX:-2048}"
BATCH="${LLAMA_SERVER_BATCH:-512}"

declare -a REQUIRED=("${SERVER_BIN}" "${MODEL_PATH}")
for target in "${REQUIRED[@]}"; do
  if [[ ! -e "${target}" ]]; then
    echo "[tinyllama-server] Missing required file: ${target}" >&2
    exit 1
  fi
  if [[ "${target}" == "${SERVER_BIN}" && ! -x "${SERVER_BIN}" ]]; then
    echo "[tinyllama-server] Server binary is not executable: ${SERVER_BIN}" >&2
    echo "Compile llama.cpp (e.g., 'cmake -B build && cmake --build build --target server') before rerunning." >&2
    exit 1
  fi

done

log_header="[tinyllama-server]"
echo "${log_header} Starting TinyLLaMA server"
echo "${log_header} Host: ${HOST}  Port: ${PORT}  Threads: ${THREADS}  Context: ${CONTEXT}  Batch: ${BATCH}"
echo "${log_header} Model: ${MODEL_PATH}"

exec "${SERVER_BIN}" \
  -m "${MODEL_PATH}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --threads "${THREADS}" \
  --ctx-size "${CONTEXT}" \
  --batch-size "${BATCH}" \
  --rope-scaling none \
  --mlock
