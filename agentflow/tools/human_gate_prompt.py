#!/usr/bin/env python3
"""Interactive human gate prompt menu using numbered input."""

import argparse
import sys
from typing import List, Optional


def display_menu(prompt: str, options: List[str]) -> str:
    """Display interactive menu and return the selected option.

    Args:
        prompt: Text to display before the menu options.
        options: List of option strings to choose from.

    Returns:
        The selected option string.

    Raises:
        ValueError: If no options provided.
        EOFError: If input stream ends unexpectedly.
    """
    if not options:
        raise ValueError("At least one option must be provided")

    # Display prompt and options
    if prompt:
        print(prompt, file=sys.stderr)

    for i, option in enumerate(options, start=1):
        print(f"  {i}) {option}", file=sys.stderr)

    # Get user input
    while True:
        try:
            user_input = input("\nEnter your choice (number): ").strip()
        except EOFError:
            raise EOFError("Input stream ended unexpectedly")

        # Validate input
        try:
            choice_num = int(user_input)
            if 1 <= choice_num <= len(options):
                return options[choice_num - 1]
            else:
                print(
                    f"Invalid choice. Please enter a number between 1 and {len(options)}.",
                    file=sys.stderr,
                )
        except ValueError:
            print("Invalid input. Please enter a valid number.", file=sys.stderr)


def main():
    """Main entry point for the human gate prompt."""
    parser = argparse.ArgumentParser(
        description="Interactive human gate prompt with numbered menu.",
        prog="human_gate_prompt",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Select an option:",
        help="Prompt text to display before options",
    )
    parser.add_argument(
        "--options",
        nargs="+",
        required=True,
        help="Menu options to choose from",
    )

    args = parser.parse_args()

    try:
        selected_option = display_menu(args.prompt, args.options)
        print(selected_option)
        return 0
    except (ValueError, EOFError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
