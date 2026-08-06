# v2 availability tests

These cover the **v2 plug-in** described in [docs/06 §B](../../../docs/06-availability-strategy.md):
the derivation rule, the community protocol, the MBFS feed path and the decay worker. They exercise
code that has **no v1 callers** — it sits behind the provider seam and is wired by one line in
`main.py` when M3 starts (docs/14).

They are not part of the v1 gate: `docs/13` puts derivation at priority 1 *for v2* and says plainly
that "a pure function with no callers is not worth testing" in v1. They run here so that M3 starts
from a green suite rather than from a blank page, and so the seam's other side is known to work.

Run them explicitly:

```bash
make test-v2        # or: uv run pytest api/tests/v2
```
