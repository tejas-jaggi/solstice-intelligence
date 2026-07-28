# Solstice Intelligence

> A governed natural-language analytics assistant that enables business users to query a certified dimensional data warehouse using plain English while validating every AI-generated SQL statement before execution.

---

## Overview

Solstice Intelligence is an end-to-end natural-language analytics system designed to bridge business users and analytical data warehouses.

Instead of allowing large language models to execute SQL directly, Solstice introduces a governed architecture that validates every generated query before execution using an allowlist-first validation pipeline.

The project demonstrates how modern AI systems can be built with engineering discipline, emphasizing correctness, transparency, and safety rather than relying solely on model capabilities.

---

## Key Features

- Natural-language analytics powered by the OpenAI Responses API
- SQL generation with semantic grounding
- sqlglot AST validation layer
- Allowlist-first warehouse validation
- Read-only SQL execution
- Typed response models
- Layered architecture with ADR-driven design
- Comprehensive automated testing

---

## Architecture

```text
Natural Language Question
            │
            ▼
Schema Grounding
            │
            ▼
OpenAI Responses API
            │
            ▼
SQL Validation Gate
(sqlglot AST + Allowlist)
            │
      ApprovedQuery
            │
            ▼
Read-only Executor
            │
            ▼
DuckDB Warehouse
            │
            ▼
Structured Assistant Response
```

---

## Repository Structure

```text
solstice-intelligence/
│
├── docs/
├── adr/
├── python/
├── sql/
├── tests/
├── assets/
├── README.md
└── LICENSE
```

---

## Technology Stack

- Python
- OpenAI Responses API
- DuckDB
- sqlglot
- SQL
- Git
- VS Code

---

## Engineering Principles

Solstice Intelligence follows several design principles:

- Business problem first
- AI output is never trusted by default
- Validation before execution
- Read-only analytics
- Layered architecture
- Strong typing
- Architecture Decision Records (ADRs)
- Test-driven engineering where practical

---

## Milestone 1 Status

✅ Warehouse integration complete

✅ Semantic grounding complete

✅ SQL validation gate complete

✅ Execution engine complete

✅ Response formatting complete

✅ End-to-end pipeline verified

✅ OpenAI Responses API integration verified

✅ Automated test suite passing

Milestone 1 establishes the complete governed backend architecture.

Future milestones will introduce API endpoints, user interface, and deployment capabilities.

---

## Example Workflow

User asks:

> How many orders are in the warehouse?

Pipeline:

Question

↓

Semantic grounding

↓

OpenAI SQL generation

↓

AST validation

↓

ApprovedQuery

↓

Read-only execution

↓

Structured response

---

## Repository Philosophy

This repository emphasizes production-minded engineering practices over model demonstrations.

The objective is not simply to convert natural language into SQL, but to demonstrate how AI-assisted analytical systems can be built with validation, transparency, and maintainability suitable for real-world business environments.

---

## Roadmap

### Milestone 1
- Complete governed backend architecture
- Automated validation
- End-to-end execution

### Milestone 2
- FastAPI service
- Streamlit interface
- Interactive analytics

### Milestone 3
- Deployment
- Authentication
- Extended business capabilities

---

## License

MIT License

---

## Author

**Tejas Jaggi**

MS in Information Management

University of Illinois Urbana-Champaign