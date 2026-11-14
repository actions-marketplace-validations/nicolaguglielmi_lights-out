#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-intake-answer (docs/adr/0090 §2): the product role again, from
# `intake-questions`, after ./go answer recorded the person's answer. The
# same run as interview.
exec sh core/steps/interview.sh
