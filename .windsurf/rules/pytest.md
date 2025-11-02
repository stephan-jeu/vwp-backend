---
trigger: always_on
description:
globs:
---
# Rules for Creating Pytest Unit Tests

## 1. Structure & Naming Convention
- All test files MUST be located in the `/tests` directory, mirroring the application's structure (e.g., a test for `app/services/user_service.py` should be in `tests/services/test_user_service.py`).
- Test files MUST be named `test_*.py`.
- Test functions MUST be named `test_*()`, with the name clearly describing the behavior being tested (e.g., `def test_create_user_with_duplicate_email_raises_http_exception():`).

## 2. Test Philosophy & Style
- **AAA Pattern:** Every test MUST follow the "Arrange, Act, Assert" pattern, separated by blank lines for clarity.
- **Isolation:** Tests MUST be completely independent. A test cannot depend on another test running before it.
- **Focus:** Each test function should test one specific behavior or outcome. Avoid testing multiple things in a single function.

- **Tests MUST focus on behavior, not implementation.** This is the most important rule. A test should verify the *outcome* of an action, not the specific steps the code took to get there. This makes tests resilient to refactoring.

- **DO Assert Against the Public Outcome:** ✅
  - The final return value of the function.
  - The observable side effects (e.g., a mock of the database shows a new record was added).
  - That an external dependency (a mock) was called with the correct arguments.

- **DO NOT Assert Against Internal Implementation:** ❌
  - Avoid checking which private helper methods were called.
  - Avoid asserting the value of internal variables that are not part of the final output.
  - Do not write tests that rely on a specific internal algorithm being used.

- **Test Naming MUST Describe Behavior:** Test names should clearly state the condition and the expected outcome.
  - **Good (Behavior):** `def test_create_user_with_duplicate_email_raises_exception():`
  - **Bad (Implementation):** `def test_user_creation_fails_on_db_integrity_check():`

## 3. Mocking & Dependencies
- Use the `pytest-mock` library (via the `mocker` fixture) for all mocking.
- **Unit Test Scope:** You MUST mock all external dependencies. This includes database calls, external API requests, file system access, and calls to other services.
- The goal is to test the logic of a single function or class in isolation, not its integration with other parts of the system.

## 4. Fixtures
- Use pytest fixtures for setting up reusable test data or objects (e.g., creating a user model instance, a test client).
- Shared fixtures that can be used across multiple test files should be placed in a `tests/conftest.py` file.
