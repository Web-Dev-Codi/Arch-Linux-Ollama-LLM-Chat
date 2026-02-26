---
trigger: manual
description:  This file contains persistent instructions for AI-assisted Python development. Follow these rules when generating, reviewing, or modifying Python code.

---

## 1. CODE STYLE & FORMATTING

### 1.1 Core PEP 8 Standards

- Use 4 spaces for indentation (never tabs)
- Maximum line length: 88 characters (Black/Ruff standard)
- Use snake_case for functions, variables, and module names
- Use PascalCase for class names and exceptions
- Use UPPER_SNAKE_CASE for constants
- One import per line, grouped: stdlib → third-party → local
- Two blank lines between top-level definitions, one between methods

### 1.2 Modern Type Hints (Python 3.10+)

```python
# ALWAYS use modern syntax:
def find_user(user_id: int) -> User | None:  # NOT Optional[User]
    pass

def process(data: list[dict[str, str]]) -> list[str]:  # NOT List[Dict[str, str]]
    pass

# Use type aliases for complex types:
UserDict = dict[str, str | int]
```

**RULE:** Always include type hints for function parameters and return values. Use `| None` instead of `Optional[X]`. Use built-in generics (`list`, `dict`, `set`) instead of `typing.List`, etc.

### 1.3 Docstrings (PEP 257)

- Every public module, class, and function MUST have a docstring
- Use triple double quotes (`"""`)
- Use Google-style format for consistency
- **NEVER duplicate type information** from annotations in docstrings
- Comments explain WHY, not WHAT (if code needs comments explaining what, rename variables)

```python
def calculate_discount(price: float, rate: float) -> float:
    """Calculate final price after applying discount rate.
    
    Args:
        price: Original price before discount
        rate: Discount rate as decimal (0.1 = 10%)
        
    Returns:
        Final price after discount applied
        
    Raises:
        ValueError: If rate is negative or greater than 1
    """
```

### 1.4 Tooling Configuration

**ALWAYS use these tools together:**

- **Ruff** for linting, formatting, import sorting (replaces flake8, Black, isort, pyupgrade, bandit)
- **mypy** or **Pyright** for type checking
- **pre-commit** for automated checks

**Sample .pre-commit-config.yaml:**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
```

## 2. NAMING CONVENTIONS

| Type | Convention | Example | Notes |
|------|-----------|---------|-------|
| Variables, functions | `snake_case` | `user_count`, `get_user()` | Descriptive, no abbreviations |
| Classes, Exceptions | `PascalCase` | `UserService`, `ValidationError` | End exceptions with "Error" |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` | Module-level only |
| Private attributes | `_leading_underscore` | `_cache`, `_internal_state` | Single underscore |
| Name mangling | `__double_leading` | `__secret` | Rare, class-private only |
| Special methods | `__dunder__` | `__init__`, `__str__` | Never invent new dunders |

**RULES:**

- Boolean variables/functions MUST read as questions: `is_valid`, `has_permission`, `can_edit`
- Avoid type-encoding: use `users` not `user_list`, `total` not `total_int`
- Never use single letters except loop counters (`i`, `j`, `k`) and math (`x`, `y`, `n`)
- Avoid Hungarian notation entirely

## 3. DESIGN PATTERNS & ARCHITECTURE

### 3.1 Prefer Language Features Over Formal Patterns

**RULE:** Always use Python's native features before implementing classical patterns assigned to you.

| Pattern | Python Approach |
|---------|----------------|
| Singleton | Module-level variable (modules are singletons) |
| Factory | Dictionary of callables or simple function |
| Strategy | Pass functions directly as arguments |
| Iterator | Generators and `__iter__`/`__next__` |
| Decorator (structural) | `@decorator` syntax |
| Observer | Callback lists, no formal Subject/Observer |

**Example - Factory as dict dispatch:**

```python
# GOOD - Pythonic
_serializers = {"json": JsonSerializer, "xml": XmlSerializer}

def get_serializer(format: str) -> Serializer:
    if cls := _serializers.get(format):
        return cls()
    raise ValueError(f"Unknown format: {format}")

# BAD - Unnecessary class hierarchy
class SerializerFactory(ABC):
    @abstractmethod
    def create_serializer(self) -> Serializer: ...
```

### 3.2 SOLID Principles with Protocols

**Single Responsibility:**

- One class = one reason to change
- Extract into focused modules/functions

**Open/Closed - Use Protocol for extension:**

```python
from typing import Protocol

class HasArea(Protocol):
    def area(self) -> float: ...

def total_area(shapes: list[HasArea]) -> float:
    return sum(s.area() for s in shapes)
```

**Interface Segregation:**

- Multiple small Protocols > one large interface
- Functions depend only on what they need

**Dependency Inversion:**

```python
# GOOD - Depend on Protocol
class NotificationService:
    def __init__(self, sender: MessageSender):  # Protocol
        self._sender = sender

# BAD - Depend on concrete class
class NotificationService:
    def __init__(self, sender: EmailSender):  # Concrete
        self._sender = sender
```

### 3.3 Composition Over Inheritance

**RULE:** Keep inheritance hierarchies to 1-2 levels max. Prefer composition.

```python
# GOOD - Composition
class Logger:
    def __init__(self, filters: list[Filter], handlers: list[Handler]):
        self.filters = filters
        self.handlers = handlers

# BAD - Deep inheritance
class FilteredSocketLogger(FilteredLogger, SocketLogger):
    pass
```

### 3.4 Dependency Injection Pattern

**ALWAYS use constructor injection with Protocols:**

```python
from typing import Protocol

class MessageSender(Protocol):
    def send(self, message: str) -> None: ...

class EmailSender:
    def send(self, message: str) -> None:
        # implementation

class NotificationService:
    def __init__(self, sender: MessageSender):
        self._sender = sender

# Composition root
service = NotificationService(EmailSender())
```

## 4. CLEAN CODE PRINCIPLES

### 4.1 Core Rules

- **DRY (Don't Repeat Yourself):** Extract duplicated logic, but follow Rule of Three (wait for 3 occurrences)
- **Composition > Inheritance:** Assemble behavior from components
- **Early Returns:** Reduce nesting, fail fast

### 4.2 Function Design

- Functions MUST do one thing
- **Maximum 2 parameters** (use dataclasses/TypedDict for more)
- No boolean flag parameters (split into two functions)
- Replace magic numbers with named constants

```python
# GOOD
SECONDS_IN_DAY = 86400
time.sleep(SECONDS_IN_DAY)

# BAD
time.sleep(86400)
```

### 4.3 Avoid These Anti-Patterns

- **Mutable default arguments:** ALWAYS use `None` sentinel

  ```python
  # GOOD
  def append_to(item, target: list | None = None) -> list:
      if target is None:
          target = []
      target.append(item)
      return target
  
  # BAD
  def append_to(item, target: list = []):  # NEVER DO THIS
      target.append(item)
      return target
  ```

- **God classes:** Classes that do too many things
- **Circular imports:** Restructure into layers or use `TYPE_CHECKING`
- **Bare except:** Always catch specific exceptions
- **Wildcard imports:** Never use `from module import *`
- **Getters/setters:** Use `@property` instead

## 5. PROJECT STRUCTURE

### 5.1 Standard src Layout

**ALWAYS use src layout for packages:**

```
project/
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── config.py
│       ├── core/
│       ├── services/
│       └── utils/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── .python-version
├── pyproject.toml
├── uv.lock
└── README.md
```

### 5.2 Web API Structure (FastAPI/Django)

**Domain-driven organization:**

```
src/package/
├── auth/
│   ├── router.py       # HTTP endpoints
│   ├── schemas.py      # Pydantic models
│   ├── models.py       # DB models
│   ├── service.py      # Business logic
│   └── dependencies.py
├── users/
├── posts/
├── config.py
├── database.py
└── main.py
```

**Data flow:** `routers → services → repositories → models`

### 5.3 Configuration

**Use pyproject.toml as single source of truth:**

```toml
[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["fastapi", "pydantic-settings"]

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.mypy]
strict = true
```

**Use uv for dependency management:**

- `uv add package` to add dependencies
- `uv sync --locked` in CI
- Always commit `uv.lock`

## 6. SECURITY BEST PRACTICES

### 6.1 Input Validation & Injection Prevention

- **NEVER use string interpolation** for SQL, shell commands, or file paths
- **SQL:** Use parameterized queries or ORM query builders only
- **Shell:** Use `subprocess.run([cmd, arg1, arg2])`, never `shell=True` with user input
- **Deserialization:** Use JSON/MessagePack, NOT pickle for untrusted data
- **YAML:** Use `yaml.safe_load()`, never `yaml.load()`
- **Path traversal:** Always resolve and validate paths

```python
# GOOD - SQL
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# BAD - SQL injection risk
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# GOOD - Path validation
UPLOAD_DIR = Path("/uploads").resolve()
requested = (UPLOAD_DIR / filename).resolve()
if not str(requested).startswith(str(UPLOAD_DIR)):
    raise ValueError("Path traversal detected")
```

### 6.2 Secrets Management

- **NEVER hardcode secrets** in code
- Use `pydantic-settings` with environment variables
- Keep `.env` in `.gitignore`, commit `.env.example`
- Use cloud secret managers in production (AWS Secrets Manager, Vault)
- Use `secrets` module for cryptographic tokens (NEVER `random`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    api_key: str
    
    class Config:
        env_file = ".env"
```

### 6.3 Password & Cryptography

- **Hash passwords with Argon2id or bcrypt** (NEVER MD5/SHA alone)
- Use `secrets.token_urlsafe()` for tokens
- Implement rate limiting on authentication endpoints

### 6.4 Dependency Security

- Run `pip-audit` in CI
- Use Dependabot or Snyk for automated vulnerability scanning
- Pin dependencies with hashes via lock files

### 6.5 API Security

- **Validate all inputs** with Pydantic models
- Configure CORS with explicit allow-lists (NEVER `["*"]` in production)
- Implement rate limiting
- Use short-lived JWTs with refresh tokens
- Validate JWT claims: expiration, issuer, audience

## 7. ERROR HANDLING & EXCEPTIONS

### 7.1 Exception Handling Rules

- **ALWAYS catch specific exceptions**, never bare `except:`
- Use `raise NewError("msg") from original_error` to preserve traceback
- Create custom exception hierarchy rooted in `AppError`
- Use context managers for resource cleanup
- Log exceptions with `logger.exception()` for full tracebacks

```python
class AppError(Exception):
    """Base exception for application errors."""

class ValidationError(AppError):
    """Raised when validation fails."""

class DatabaseError(AppError):
    """Raised when database operations fail."""

# Usage
try:
    result = risky_operation()
except ExternalError as e:
    raise DatabaseError("Failed to save user") from e
```

### 7.2 Context Managers for Resources

```python
# GOOD - Guaranteed cleanup
with open(file_path) as f:
    data = f.read()

# GOOD - Custom context manager
from contextlib import contextmanager

@contextmanager
def database_transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

## 8. LOGGING BEST PRACTICES

### 8.1 Logging Rules

- Use `logging.getLogger(__name__)` in every module
- **NEVER use print() in production code**
- Use `structlog` for structured JSON logging
- Configure logging once at application entry point
- Follow log levels: DEBUG < INFO < WARNING < ERROR < CRITICAL

```python
import structlog

logger = structlog.get_logger(__name__)

def process_user(user_id: int):
    logger.info("processing_user", user_id=user_id)
    try:
        user = get_user(user_id)
        logger.debug("user_retrieved", username=user.name)
    except Exception:
        logger.exception("user_processing_failed", user_id=user_id)
        raise
```

### 8.2 Security Logging

- **NEVER log passwords, tokens, API keys, or PII**
- Redact sensitive fields in log processors
- Attach correlation IDs via middleware
- Log to unbuffered stdout (Twelve-Factor App)

## 9. TESTING CONVENTIONS

### 9.1 Test Structure

- Use **pytest** exclusively
- Organize: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- Shared fixtures in `conftest.py`
- Test file names: `test_*.py`
- Test function names: `test_<feature>_<condition>_<expected>`

```python
# tests/unit/test_user_service.py
import pytest

def test_create_user_with_valid_data_returns_user(user_service):
    user = user_service.create(name="Alice", email="alice@example.com")
    assert user.name == "Alice"

def test_create_user_with_invalid_email_raises_validation_error(user_service):
    with pytest.raises(ValidationError):
        user_service.create(name="Bob", email="invalid")
```

### 9.2 Testing Rules

- **Mock only external boundaries** (APIs, databases, filesystems)
- Never mock internal logic
- Use `@pytest.mark.parametrize` for data-driven tests
- Aim for **80-90% coverage** minimum
- Use `pytest-asyncio` for async tests
- Use `hypothesis` for property-based testing

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sort_is_idempotent(xs):
    assert sorted(sorted(xs)) == sorted(xs)
```

### 9.3 Fixtures

```python
# conftest.py
import pytest

@pytest.fixture
def db_session():
    session = create_test_session()
    yield session
    session.close()

@pytest.fixture
def user_service(db_session):
    return UserService(db_session)
```

## 10. ASYNC/AWAIT PATTERNS

### 10.1 Async Rules

- Use `async/await` **ONLY for I/O-bound operations** (HTTP, DB, file I/O)
- For CPU-bound work, use `multiprocessing` or `ProcessPoolExecutor`
- Never mix blocking and async code (use `asyncio.to_thread()` for blocking calls)
- Use async context managers for resources

```python
import asyncio
import httpx

async def fetch_users(user_ids: list[int]) -> list[User]:
    async with httpx.AsyncClient() as client:
        tasks = [client.get(f"/users/{uid}") for uid in user_ids]
        responses = await asyncio.gather(*tasks)
        return [User.parse(r.json()) for r in responses]
```

### 10.2 Common Async Patterns

- `asyncio.gather()` for concurrent execution
- `asyncio.wait_for()` for timeouts
- `asyncio.Queue` for producer-consumer
- `asyncio.create_task()` for background tasks

## 11. PYDANTIC BEST PRACTICES

### 11.1 Configuration Management

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = Field(..., description="PostgreSQL connection string")
    redis_host: str = Field(default="localhost")
    api_key: str
    debug: bool = Field(default=False)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

# Load once at startup
settings = Settings()
```

### 11.2 Validation Models

```python
from pydantic import BaseModel, EmailStr, Field, field_validator

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)
    
    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError("Username must be alphanumeric")
        return v
```

## 12. PERFORMANCE OPTIMIZATION

### 12.1 Common Optimizations

- **List comprehensions** are 30-50% faster than append loops
- **Generator expressions** for O(1) memory: `sum(x**2 for x in range(10**7))`
- **`"".join(iterable)`** for string concatenation (NOT `+=` in loops)
- **Convert to set** for O(1) membership testing
- **`@lru_cache`** for memoization of pure functions
- **`@cached_property`** for lazy computation

```python
from functools import lru_cache, cached_property

@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class DataProcessor:
    @cached_property
    def expensive_computation(self) -> dict:
        # Computed once, cached
        return self._process_data()
```

### 12.2 Profiling

- Use `py-spy` for production (sampling profiler, low overhead)
- Use `cProfile` for development (deterministic profiling)

## 13. COMMON GOTCHAS TO AVOID

### 13.1 Critical Gotchas

1. **Mutable default arguments** - Use `None` sentinel
2. **Late-binding closures** - Use default args: `lambda x, i=i: ...`
3. **Modifying list while iterating** - Create new list via comprehension
4. **`is` vs `==`** - Use `==` for values, `is` only for `None`/`True`/`False`
5. **Integer caching** - `is` unreliable for numbers (cached -5 to 256)
6. **Catching `BaseException`** - Catch `Exception` instead

### 13.2 String/Bytes Confusion

```python
# GOOD - Explicit encoding
text = byte_string.decode("utf-8")
data = text_string.encode("utf-8")

# Handle encoding errors
text = byte_string.decode("utf-8", errors="ignore")
```

## 14. QUICK REFERENCE CHECKLIST

Before committing code, verify:

- [ ] Type hints on all public functions
- [ ] Docstrings on public modules/classes/functions
- [ ] No mutable default arguments
- [ ] Specific exception handling (no bare `except:`)
- [ ] Logging instead of print statements
- [ ] Secrets loaded from environment
- [ ] Tests for new functionality
- [ ] Ruff passes (formatting + linting)
- [ ] mypy passes (type checking)
- [ ] Functions ≤ 2 parameters
- [ ] No SQL injection risks (parameterized queries)
- [ ] Resource cleanup via context managers

## 15. WHEN TO DEVIATE

These rules represent best practices for production Python code. Deviate when:

- **Performance-critical code** requires optimization over readability
- **Legacy codebases** have established conventions (match existing style)
- **Specific frameworks** have conflicting conventions (follow framework)
- **Team consensus** differs (document in project-specific rules)

When deviating, document the reason with inline comments or ADRs (Architecture Decision Records).

---

**Last Updated:** 2026-02-24
**Target Python Version:** 3.13+
**Toolchain:** Ruff 0.8+, mypy 1.13+, pytest 8.0+, uv 0.5+
