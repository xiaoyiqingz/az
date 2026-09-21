APP_NAME := az
ENTRYPOINT := main.py
DIST_DIR := dist
BUILD_DIR := build
PYINSTALLER := uv run --group dev python -m PyInstaller
OS_NAME := $(shell uname -s)
CODESIGN_IDENTITY ?=

ifeq ($(OS_NAME),Darwin)
ifneq ($(strip $(CODESIGN_IDENTITY)),)
PYINSTALLER_PLATFORM_ARGS := --codesign-identity "$(CODESIGN_IDENTITY)"
endif
endif

PYINSTALLER_COMMON := --noconfirm --clean --name $(APP_NAME) \
	$(PYINSTALLER_PLATFORM_ARGS) \
	--collect-all pydantic_ai \
	--collect-all pydantic_ai_harness \
	--collect-all pydantic_ai_skills \
	--copy-metadata genai-prices \
	--copy-metadata fastmcp-slim \
	--copy-metadata mcp

.PHONY: help run build-onedir build-onefile

help:
	@echo "make run             - 以项目内 .az 为 AZ Home 启动"
	@echo "make build-onedir    - 构建目录式发布包：dist/onedir/az/"
	@echo "make build-onefile   - 构建单文件发布包：dist/onefile/az"

run:
	uv run main.py --az-home .az

build-onedir:
	$(PYINSTALLER) $(PYINSTALLER_COMMON) --onedir \
		--distpath $(DIST_DIR)/onedir \
		--workpath $(BUILD_DIR)/onedir \
		--specpath $(BUILD_DIR)/spec \
		$(ENTRYPOINT)

build-onefile:
	$(PYINSTALLER) $(PYINSTALLER_COMMON) --onefile \
		--distpath $(DIST_DIR)/onefile \
		--workpath $(BUILD_DIR)/onefile \
		--specpath $(BUILD_DIR)/spec \
		$(ENTRYPOINT)
