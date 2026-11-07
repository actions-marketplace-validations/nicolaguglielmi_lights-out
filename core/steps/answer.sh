#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-answer (docs/adr/0055 §2): the product role again, from `questions`,
# after ./go answer recorded the person's answer. The same run as clarify.
exec sh core/steps/clarify.sh
