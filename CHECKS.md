# Handoff verification

- Current Django and React source, migrations 0001-0008, and both runtime DOCX templates included.
- DOCX author metadata removed; document.xml preserved byte-for-byte, including public university details.
- Delivered backend: 86 tests passed on a clean in-memory SQLite database. No working database used.
- Fresh npm ci and TypeScript/Vite build passed in temporary staging; staging removed afterward.
- Final tree excludes .git, .env, keys, databases, uploaded/generated documents, archives, .venv, node_modules, dist, .local and Python caches.
- Checked against actual local password/key values without printing them. Source email addresses are synthetic fixtures. No profiles or database records copied.
- Working source left unchanged. Nothing published.

PostgreSQL tests were not rerun from this delivery folder. The isolated PostgreSQL test script is included. Each recipient configures their own new PostgreSQL database using README.md.
