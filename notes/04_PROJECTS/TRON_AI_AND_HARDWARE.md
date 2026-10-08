# Tron — AI / Local Setup

## Current PC
Known machine:
- Lenovo ThinkPad 21U3S1FD00
- Windows 11 Home
- Intel Core Ultra 7 258V
- Intel Arc 140V
- 32 GB RAM
- approximately 477 GB storage
- Vulkan 1.4.313
- recent Windows build context around 26300
- Intel graphics driver context around 32.0.101.8826

## Node
Known setup:
- Node v20.20.0
- npm 10.8.2

## Ollama
Known models/setup has included:
- `qwen2.5-coder:7b`
- `qwen3` variants
- `gemma3:4b`
- `gemma3:12b`
- `kimi-k3:cloud`
- `nomic-embed-text`

Known qwen2.5-coder setup:
- roughly 5.9 GB model
- context 16384
- KEEP_ALIVE -1
- `OLLAMA_CONTEXT_LENGTH=16384`

Ollama has previously been running on port `11434`.

## Tron AI Stack
Previously discussed/used:
- Kimi K3
- Gemma vision
- Whisper
- Piper TTS
- YOLOv8n ONNX
- Bedrock
- Claude
- embeddings / RAG

Vision performance context:
- YOLOv8n ONNX around 10–15 FPS was previously observed/planned.

## Claude Code
Aditya uses Claude Code for serious repository work.
Known configuration context:
- Claude Code 2.1.258
- Claude Opus 5
- high effort for quality
- Haiku 4.5 as small/fast model
- Bedrock
- `us-east-1`

Important preference:
- Aditya values high-quality accurate work over blindly minimizing token usage when implementing important features.
- For major changes, Claude should first read/understand the repo before coding.
