# Coding Standards

All Python and prompt files in this codebase must adhere to these standards.

## Python Coding Standards

1. **File Line Limits**:
   - Implementation files: Max 250 lines.
   - Test files: Max 350 lines.
   - Prompt/Skill files: Max 150 lines.
   - Stubs/Interfaces: Max 100 lines.
   Every file must be split by responsibility boundary if it exceeds these limits.

2. **Idempotency**: All operations, scripts, hooks, and commands must be safe to run multiple times with the same result.

3. **Validation**: Use Pydantic v2 for all structured configuration and user inputs. Do not use custom validation logic or Pydantic v1.

4. **Exception Handling**: Avoid bare `except:` statements. Always catch specific exceptions (e.g., `ValueError`, `OSError`).

5. **Subprocess Calls**: Avoid `shell=True` in subprocess/PTY calls. Use argument lists to prevent command/signal injection.

6. **Secrets & Credentials**: Never hardcode credentials, passwords, API keys, or tokens. Use environment variables. Ensure secrets are never printed to stdout or logged to files.

## Prompt & Skill Standards

1. **Silence on Internals**: Do not narrate tool calls, file paths, index caching, or internal workflow steps. Output only the requested deliverables or structured responses.
2. **Deterministic Actions**: Avoid LLM calls for deterministic logic like bundling, metadata extraction, or state management. Use python scripts.
3. **No Placeholders**: Never generate placeholder code or use stubs (like `raise NotImplementedError`) in final implementations.
