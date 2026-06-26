# Context Bundle Format

Your opening message is your complete context bundle. It has these labelled sections. Read all of them before writing code.

## TASK

What you are building and the acceptance criteria you must meet. The acceptance criteria is the definition of done — if it is not met, the PR must not be opened.

## OWNS

Files you are responsible for creating or modifying. You must not touch any file not on this list. If a file needs to exist but is not on your list, it belongs to another task.

## READS

Files you may read for reference. Do not modify them. If you need to understand an interface, read the contract stub in this list.

## CONTRACTS

Interface stubs already committed to main. Function signatures, class names, and module paths are frozen. Your implementation must satisfy them exactly. Do not change signatures.

## ARCHITECTURE

The relevant section of this project's architecture document. Understand the design intent before writing code. If your implementation would deviate from the architecture, write to the blockers file instead.

## TEST STRATEGY

This project's testing philosophy. Follow it exactly:
- Use only the mock fixtures pre-provided; do not introduce new mocking libraries.
- Do not mock internal functions of the module under test.
- Integration tests use real dependencies.
- Coverage threshold is stated here and is a hard gate for PR creation.

## TEST SCENARIOS

The specific behaviours your tests must cover. The skeleton test file already has method stubs for each. Make every one pass.

## SECURITY CONSTRAINTS

Non-negotiable requirements. Each must be satisfied in your implementation. See testing_guide.md for how to verify security properties in tests.

## CONFIG

Active configuration for this run: model, token budget, coverage threshold, file size limits.
