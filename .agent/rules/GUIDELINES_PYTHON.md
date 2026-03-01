# Engineering and Python Standards

This document defines mandatory coding, architecture, typing, and testing standards for Python 3.12+ projects, including backend services, machine learning pipelines, and FastAPI applications.

---

## 1. Python Version and Scope

- Target Python 3.12+.
- These rules apply to:
  - Core libraries and services
  - FastAPI backends
  - Machine learning and data pipelines
  - Test code, unless explicitly stated otherwise

---

## 2. Type Hinting and Correctness

### 2.1 Type System Rules

1. Use PEP 695 type parameters where appropriate.
2. Use built-in generic types:
   - `list`, `dict`, `tuple`
   - Do not use `List`, `Dict`, `Tuple`
3. Use `|` syntax instead of `Optional` or `Union`.
   - Example: `str | None`
4. Type hint:
   - All public APIs
   - Non-trivial internal logic
5. Always import `Callable` from `collections.abc`.

### 2.2 Enforcement

- Treat type checking as a bug-prevention layer, not a substitute for tests.
- Enforce static typing in CI using mypy.

---

## 3. Imports

1. All imports must appear at the top of the file.
2. Imports must never be conditional.
3. Always import `Callable` from `collections.abc`.
4. Use Keras 3.x directly.
   - Do not import TensorFlow via Keras.

---

## 4. Code Style and Formatting

### 4.1 General Style

1. Follow PEP 8 for naming, layout, and formatting.
2. Prefer automated formatting to minimize diff noise.
3. Approved formatters:
   - Black, or
   - Ruff formatter, if Ruff is standardized
4. Approved linter:
   - Ruff
5. Approved test runner:
   - pytest

### 4.2 Explicit Style Rules

1. Use the `os` module for path operations.
   - Do not use `pathlib.Path`.
2. Use `glob` only when necessary and efficient.
3. Do not prefix variables, attributes, or methods with underscores.
4. Class attributes must use `self.name`, not `self._name`.

---

## 5. Comments, Docstrings, and Separators

### 5.1 Comments

- Write comments only when necessary.
- Keep comments short and factual.

### 5.2 Docstrings

- Write docstrings only when explicitly requested.
- Required structure:
  1. Short summary
  2. Arguments
  3. Return value

### 5.3 Separators

- Classes: exactly 79 `#` characters
- Functions and methods: `#` followed by 77 `-` characters
- Do not add a separator above `__init__`.

---

## 6. Code Structure and Design Principles

### 6.1 Core Principles

1. Apply the Single Responsibility Principle to all classes and modules.
2. Group related logic into cohesive modules, services, or packages.
3. Avoid defining functions or classes inside other functions.
4. Keep logic separate from execution.
   - Example: controllers vs services vs utilities
5. Avoid over-abstraction.
   - Prefer clarity and directness over cleverness.
6. Use Dependency Injection or Inversion of Control to decouple components.

### 6.2 Object Creation

- Use Factory, Builder, or Prototype patterns when object creation is complex.

---

## 7. Architectural Guidelines by System Type

### 7.1 Frontend and UI

- Use MVC or MVVM.
- Keep rendering, state, and logic separate.
- Controllers and Views must be thin layers over core logic.

### 7.2 Backend Services and APIs

- Use Service Layer plus Repository Pattern.
- Business logic belongs in service or domain classes.
- Data access must be handled via repositories or gateway abstractions.

### 7.3 Machine Learning and Data Pipelines

- Use Pipeline, Factory, or Builder patterns.
- Keep preprocessing, training, and evaluation:
  - Modular
  - Reproducible
  - Versioned

### 7.4 Event-Driven and Asynchronous Systems

- Use Observer, Mediator, or Pub/Sub patterns.

### 7.5 Plugin and Configurable Behavior

- Use Strategy, Command, or Decorator patterns.

### 7.6 Distributed Systems

- Apply CQRS, Saga, or Event Sourcing where applicable.
- Use only when justified by system complexity.

---

## 8. Testing and Validation

### 8.1 General Testing Rules

1. Follow Arrange–Act–Assert.
2. Prefer readable, isolated tests.
3. Mock or stub dependencies for unit isolation.
4. Cover:
   - Normal cases
   - Edge cases
   - Failure cases

### 8.2 Test Types

- Use the appropriate mix of:
  - Unit tests
  - Integration tests
  - Contract tests
  - End-to-end tests

---

## 9. FastAPI Best Practices

### 9.1 Application Structure

1. Split endpoints into routers.
2. Compose routers into the application.
3. Keep modules cohesive and scalable.

### 9.2 Dependency Injection

- Use FastAPI dependencies to centralize:
  - Authentication
  - Authorization
  - Database sessions
  - Request-scoped resources

### 9.3 Validation and Schemas

- Use Pydantic models and type annotations.
- Avoid manual validation when schemas can express constraints.
- Rely on type hints for OpenAPI generation.

### 9.4 Async and Performance

1. Use `async def` only when the full I/O stack is non-blocking.
2. Avoid blocking calls inside async endpoints.
3. Use async-compatible libraries for HTTP and database access when async is chosen.
4. Keep endpoints synchronous if async provides no real benefit.

### 9.5 Background and Long-Running Workloads

1. Use `BackgroundTasks` for post-response work.
2. Do not run CPU-bound or heavy workloads in request handlers.
3. Offload heavy work to job queues and separate workers.

### 9.6 Testing FastAPI Applications

1. Use dependency overrides to replace real dependencies with fakes.
2. Prefer a consistent app initialization in tests.
3. Isolate shared state to prevent test flakiness.

---

## 10. Tooling Baseline Summary

- Formatter: Black or Ruff formatter
- Linter: Ruff
- Type checker: mypy
- Test runner: pytest
