# ==============================================================================
# Auto-generated Hardware Preparation Makefile for ${config.project.name}
# ==============================================================================

MANIFEST ?= ${rel_manifest_path}
LOCKFILE ?= Bender.lock

.PHONY: update-hw
update-hw: $(LOCKFILE)

$(LOCKFILE):
	@echo "\n[MAKE] Resolving and downloading hardware dependencies via Bender..."
	bender update