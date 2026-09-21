PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup app offline enrich discover snapshot verify test fmt

setup:
	/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

app:
	.venv/bin/streamlit run app.py

offline:
	DATA_BEARS_OFFLINE=1 .venv/bin/streamlit run app.py

enrich:
	$(PY) scripts/discover_indicators.py --enrich

discover:
	$(PY) scripts/discover_indicators.py --search "$(Q)"

snapshot:
	$(PY) scripts/snapshot.py

verify-sources:
	$(PY) scripts/verify_sources.py

verify:
	$(PY) scripts/verify_endpoints.py
	$(PY) scripts/verify_join.py
	$(PY) scripts/verify_sources.py

test:
	.venv/bin/pytest -q

fmt:
	.venv/bin/black --line-length 88 .
