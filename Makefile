.PHONY: install install-dev deps test lint clean run snapshot

install:
	pip install -r requirements.lock

install-dev:
	pip install -r requirements.lock
	pip install -r requirements-dev.lock

deps:
	pip-compile requirements.in --generate-hashes -o requirements.lock
	pip install -r requirements.lock

test:
	python -m pytest tests/ -v $(ARGS)

test-cov:
	python -m pytest tests/ --cov=. --cov-report=term-missing -v

lint:
	python -m py_compile paper_trading/engine.py paper_trading/serve.py paper_trading/ops/monitor.py
	python -m py_compile features/labels.py risk/position_sizing.py monitoring/validity_state_machine.py

run:
	PYTHONPATH=$$PYTHONPATH:. python -m paper_trading.ops.monitor

snapshot:
	python scripts/generate_snapshot.py

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
