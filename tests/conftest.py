# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Shared pytest configuration for the test suite."""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign the ``unit`` marker to any test not already marked ``integration``/``e2e``.

    This makes the unit/integration/e2e tiers real and runnable
    (``pytest -m unit`` / ``-m integration`` / ``-m e2e``) without hand-marking
    every test, and stays correct as tests are added. Explicit markers always win.
    """
    for item in items:
        if not any(item.get_closest_marker(name) for name in ("integration", "e2e")):
            item.add_marker(pytest.mark.unit)
