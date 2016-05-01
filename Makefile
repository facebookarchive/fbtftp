PYTHON=python3
PYTHON3 := $(shell command -v python3)
PYTHON35 := $(shell command -v python3.5)
ifndef PYTHON3
	ifdef PYTHON35
		PYTHON=python3.5
	endif
endif
PYTHON_MAJOR_AT_LEAST=3
PYTHON_MINOR_AT_LEAST=3
PYTHON_VERSION := $(shell $(PYTHON) -c 'from __future__ import print_function; import platform; print(platform.python_version())')
CHECK_PYTHON_VERSION=$(shell $(PYTHON) -c 'from __future__ import print_function; import sys; print(0) if sys.version_info[:2] < ($(PYTHON_MAJOR_AT_LEAST), $(PYTHON_MINOR_AT_LEAST)) else print(1)')

.PHONY: all install test clean

all: test install

install:
ifneq ($(CHECK_PYTHON_VERSION), 1)
	@echo Invalid Python version, need at least $(PYTHON_MAJOR_AT_LEAST).$(PYTHON_MINOR_AT_LEAST), found "$(PYTHON_VERSION)"
	@exit 1
endif
	${PYTHON} setup.py install

test:
ifneq ($(CHECK_PYTHON_VERSION), 1)
	@echo Invalid Python version, need at least $(PYTHON_MAJOR_AT_LEAST).$(PYTHON_MINOR_AT_LEAST), found "$(PYTHON_VERSION)"
	@exit 1
endif
	${PYTHON} setup.py test
	${PYTHON} setup.py flake8

clean:
	$(RM) -r build/ dist/ fbtftp.egg-info/ tests/fbtftp.egg-info .coverage \
	.eggs/ fbtftp/__pycache__/ tests/__pycache__
