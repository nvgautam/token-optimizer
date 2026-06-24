"""Interactive oracle conversation loop."""

from __future__ import annotations

from pathlib import Path

import anthropic

from agentflow.config.schema import AgentFlowConfig
from agentflow.oracle.artifact_generator import generate_artifacts
from agentflow.oracle.checklist import ChecklistState, evaluate_checklist, new_checklist_state


def _load_prompt(filename: str) -> str:
    try:
        from importlib.resources import files
        return files("agentflow.prompts.oracle.v1").joinpath(filename).read_text()
    except Exception:
        fallback = Path(__file__).parent.parent / "prompts" / "oracle" / "v1" / filename
        return fallback.read_text()


class OracleConversation:
    def __init__(self, project_root: Path, config: AgentFlowConfig):
        self.project_root = project_root
        self.config = config
        self.history: list[dict] = []
        self.checklist_state: ChecklistState = new_checklist_state()
        self._system_prompt: str = _load_prompt("system.md")

    def chat(self, user_message: str) -> str:
        """Send user message, get response, update checklist. Returns assistant text."""
        self.history.append({"role": "user", "content": user_message})

        client = anthropic.Anthropic()
        try:
            response = client.messages.create(
                model=self.config.models.oracle,
                max_tokens=4096,
                system=self._system_prompt,
                messages=self.history,
            )
        except (anthropic.AuthenticationError, TypeError):
            raise EnvironmentError(
                "No credentials found. Set ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, "
                "or run `ant auth login`."
            )
        assistant_text = response.content[0].text
        self.history.append({"role": "assistant", "content": assistant_text})

        self.checklist_state = evaluate_checklist(self.history, self.checklist_state)
        return assistant_text

    def should_propose_generation(self) -> bool:
        return self.checklist_state.all_resolved

    def generation_proposal(self) -> str:
        return (
            "\nI have enough to generate the architecture and task plan. "
            "Shall I proceed, or is there more to discuss? (yes/no)"
        )

    def run_interactive(self) -> None:
        """Run the full interactive CLI loop."""
        print("AgentFlow Design Oracle — type 'exit' to quit without generating.\n")
        print("Oracle: Tell me about your project. What are you building?\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Exiting without generating artifacts.")
                break

            response = self.chat(user_input)
            print(f"\nOracle: {response}\n")

            if self.should_propose_generation():
                print(self.generation_proposal())
                try:
                    confirm = input("You: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = "no"

                if confirm in ("yes", "y"):
                    print("\nGenerating artifacts…")
                    result = generate_artifacts(self.history, self.project_root, self.config)
                    print(
                        f"\nDone. Generated {result['task_count']} tasks, "
                        f"{result['contract_count']} contract files.\n"
                        f"architecture.md → {result['architecture_path']}\n"
                        f"tasks.json      → {result['tasks_path']}"
                    )
                    break
                else:
                    print("\nOracle: Understood — let's keep going. What else?\n")
