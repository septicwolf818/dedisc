#!/usr/bin/env make
# Dedisc Makefile – manage build, run, install, uninstall
#
#   make run        – create local venv (Python 3.14), build patched pycdio,
#                     install deps, run the app from source
#   make install    – install into user space, create launcher + desktop entry + icon
#   make uninstall  – remove installed user files and venv
#   make clean      – remove local venv and __pycache__

PYTHON_BIN := python3.14
APP_ID := pl.septicwolf818.Dedisc
APP_NAME := Dedisc
INSTALL_DIR := $(HOME)/.local/share/$(APP_NAME)
VENV_DIR := $(INSTALL_DIR)/venv
BIN_DIR := $(HOME)/.local/bin
DESKTOP_DIR := $(HOME)/.local/share/applications
ICON_DIR := $(HOME)/.local/share/icons/hicolor/scalable/apps

SRC_DIR := $(CURDIR)

# ANSI colors
BOLD   := \033[1m
CYAN   := \033[36m
GREEN  := \033[32m
YELLOW := \033[33m
RED    := \033[31m
RESET  := \033[0m

# Print a step message (hidden command, colored output)
step = @printf '$(CYAN)==>$(RESET) $(BOLD)%s$(RESET)\n' "$(1)"
ok   = @printf '$(GREEN)✓ %s$(RESET)\n' "$(1)"

.PHONY: all run install uninstall clean check-python

all: run

check-python:
	@command -v $(PYTHON_BIN) >/dev/null 2>&1 || { \
		printf '$(RED)✗ Python $(PYTHON_BIN) not found. Please install Python 3.14.$(RESET)\n'; exit 1; \
	}

run: check-python
	$(call step,Creating local Python 3.14 virtual environment)
	@$(PYTHON_BIN) -m venv .venv
	$(call step,Upgrading pip, wheel and setuptools)
	@.venv/bin/pip install --upgrade pip wheel setuptools >/dev/null 2>&1
	$(call step,Building patched pycdio for Python 3.14)
	@rm -rf /tmp/pycdio-build && mkdir -p /tmp/pycdio-build
	@.venv/bin/pip download --no-deps --no-binary :all: pycdio==2.1.1 -d /tmp/pycdio-build >/dev/null 2>&1
	@tar xf /tmp/pycdio-build/pycdio-*.tar.gz -C /tmp/pycdio-build
	@cd /tmp/pycdio-build/pycdio-2.1.1 && patch -p1 < $(SRC_DIR)/pycdio-py314.patch >/dev/null
	@.venv/bin/pip install /tmp/pycdio-build/pycdio-2.1.1/ >/dev/null 2>&1
	@rm -rf /tmp/pycdio-build
	$(call step,Installing runtime dependencies)
	@grep -v '^pycdio' requirements.txt | .venv/bin/pip install -r /dev/stdin >/dev/null 2>&1
	$(call step,Launching Dedisc)
	@PYTHONPATH=$(CURDIR) .venv/bin/python src/main.py 2>&1 | tee -a $(HOME)/.local/share/Dedisc/dedisc-run.log

install: check-python
	$(call step,Installing Dedisc to $(INSTALL_DIR))
	@mkdir -p "$(INSTALL_DIR)" "$(BIN_DIR)" "$(DESKTOP_DIR)" "$(ICON_DIR)"
	$(call step,Copying source tree and assets)
	@cp -a src "$(INSTALL_DIR)/"
	@cp -a po "$(INSTALL_DIR)/" 2>/dev/null || true
	@cp -a data "$(INSTALL_DIR)/" 2>/dev/null || true
	@cp -a requirements.txt "$(INSTALL_DIR)/"
	@cp -a pycdio-py314.patch "$(INSTALL_DIR)/"
	$(call step,Compiling and installing translations)
	@mkdir -p "$(INSTALL_DIR)/locale/pl/LC_MESSAGES"
	@msgfmt -o "$(INSTALL_DIR)/locale/pl/LC_MESSAGES/dedisc.mo" "$(SRC_DIR)/po/pl.po" 2>/dev/null || true
	$(call step,Creating virtual environment)
	@if [ ! -d "$(VENV_DIR)" ]; then $(PYTHON_BIN) -m venv "$(VENV_DIR)"; fi
	$(call step,Upgrading pip, wheel and setuptools)
	@"$(VENV_DIR)/bin/pip" install --upgrade pip wheel setuptools >/dev/null 2>&1
	$(call step,Building patched pycdio for Python 3.14)
	@rm -rf /tmp/pycdio-build && mkdir -p /tmp/pycdio-build
	@"$(VENV_DIR)/bin/pip" download --no-deps --no-binary :all: pycdio==2.1.1 -d /tmp/pycdio-build >/dev/null 2>&1
	@tar xf /tmp/pycdio-build/pycdio-*.tar.gz -C /tmp/pycdio-build
	@cd /tmp/pycdio-build/pycdio-2.1.1 && patch -p1 < "$(INSTALL_DIR)/pycdio-py314.patch" >/dev/null
	@"$(VENV_DIR)/bin/pip" install /tmp/pycdio-build/pycdio-2.1.1/ >/dev/null 2>&1
	@rm -rf /tmp/pycdio-build
	$(call step,Installing runtime dependencies)
	@grep -v '^pycdio' "$(INSTALL_DIR)/requirements.txt" | "$(VENV_DIR)/bin/pip" install -r /dev/stdin >/dev/null 2>&1
	$(call step,Creating launcher at $(BIN_DIR)/$(APP_NAME))
	@printf '#!/usr/bin/env bash\nVENV="%s"\nAPP_DIR="%s"\nexport PYTHONPATH="$${APP_DIR}"\nexec "$${VENV}/bin/python3" "$${APP_DIR}/src/main.py" "$$@"\n' \
		"$(VENV_DIR)" "$(INSTALL_DIR)" > "$(BIN_DIR)/$(APP_NAME)"
	@chmod +x "$(BIN_DIR)/$(APP_NAME)"
	$(call step,Writing desktop entry)
	@sed -e 's|@APP_ID@|$(APP_ID)|g' -e 's|@BIN_PATH@|$(BIN_DIR)/$(APP_NAME)|g' \
		"$(SRC_DIR)/data/dedisc.desktop.in" > "$(DESKTOP_DIR)/$(APP_ID).desktop"
	$(call step,Installing icon)
	@cp "$(SRC_DIR)/data/pl.septicwolf818.Dedisc.svg" "$(ICON_DIR)/$(APP_ID).svg"
	$(call step,Registering desktop database and icon cache)
	@gtk-update-icon-cache -f "$(HOME)/.local/share/icons/hicolor" >/dev/null 2>&1 || true
	@update-desktop-database "$(DESKTOP_DIR)" >/dev/null 2>&1 || true
	$(call ok,Dedisc installed to $(INSTALL_DIR))

uninstall:
	$(call step,Removing install directory $(INSTALL_DIR))
	@rm -rf "$(INSTALL_DIR)"
	$(call step,Removing launcher $(BIN_DIR)/$(APP_NAME))
	@rm -f "$(BIN_DIR)/$(APP_NAME)"
	$(call step,Removing desktop entry)
	@rm -f "$(DESKTOP_DIR)/$(APP_ID).desktop"
	$(call step,Removing icon)
	@rm -f "$(ICON_DIR)/$(APP_ID).svg"
	$(call step,Removing any system-wide copy)
	@rm -f "/usr/share/applications/$(APP_ID).desktop" 2>/dev/null || true
	@update-desktop-database "$(DESKTOP_DIR)" >/dev/null 2>&1 || true
	$(call ok,Dedisc removed.)

clean:
	$(call step,Removing local venv and build cache)
	@rm -rf .venv /tmp/pycdio-build
	$(call step,Removing __pycache__ directories)
	@find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	$(call ok,Clean done.)
