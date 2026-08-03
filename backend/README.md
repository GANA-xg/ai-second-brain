# Backend testing

Run the backend test suite from this directory:

```bash
pytest
```

For the focused Part 17 coverage:

```bash
pytest tests/test_rag_golden.py tests/test_integration_smoke.py tests/test_files.py
```

If your environment requires project variables, load `backend/.env` first.
