"""
Provider registry package (TD-01 v0.9 — see
`Build-out/02 Classification/TD-01 Provider Architecture — Design Package.md`).

Deliberately empty beyond this docstring: `registry.py` owns the registry
itself (no dependency on any concrete provider), and each concrete provider
module (`claude.py` today; a future `openai.py`/`ollama.py`/etc. would follow
the same shape) registers itself as a side effect of being imported — see
`registry.py`'s own docstring for why importing a provider module is what
"activates" it, and `src/main.py`'s import of `src.providers.claude` for the
one place that import currently happens.
"""
