# Copiright Fondazione Chips-IT
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#

OLLIVANDER_ROOT := $(shell pwd)

include ollivander.mk

# Include the test suite to run validation checks on the Ollivander 
# development environment using the provided example projects.
include soc_cfg_examples/ollivander_test.mk
