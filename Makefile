# Ecosystems Evaluate - Makefile

.PHONY: help venv install test clean clean-all

help:
	@echo "Ecosystems Evaluate - Dependency Analysis Tool"
	@echo ""
	@echo "Commands:"
	@echo "  make venv       Create virtual environment"
	@echo "  make install    Install dependencies"
	@echo "  make test       Run tests"
	@echo "  make clean      Clean up results"
	@echo "  make clean-all  Clean results and venv"

# Create virtual environment
venv:
	@if [ ! -d "venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
		echo "Virtual environment created"; \
	else \
		echo "Virtual environment already exists"; \
	fi

# Install the package (editable) into the virtual environment
install: venv
	@echo "Installing dependencies..."
	@. venv/bin/activate && pip install --upgrade pip
	@. venv/bin/activate && pip install -e .
	@echo ""
	@echo "Installation complete!"

# Run tests
test: venv
	@echo "Running tests..."
	@. venv/bin/activate && python -m unittest discover tests/ -v
	@echo "Tests completed!"

# Clean analysis output files
clean:
	@rm -f analysis.json analysis_*.json *-analysis.json
	@echo "Analysis files cleaned"

# Clean everything including venv
clean-all: clean
	@rm -rf venv/
	@echo "Complete cleanup done"
