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
"""Entity-resolution mixin for DCClient (names, types, place resolution)."""

from datacommons_mcp.data_models.search import NodeInfo


class _EntitiesMixin:
    """Entity name/type lookup and place resolution methods for DCClient."""

    async def fetch_entity_names(self, dcids: list[str]) -> dict:
        response = self.dc.node.fetch_entity_names(entity_dcids=dcids)
        return {dcid: name.value for dcid, name in response.items() if name}

    async def fetch_entity_infos(self, dcids: list[str]) -> dict[str, NodeInfo]:
        """Fetch entity information including name and type for a list of DCIDs."""

        # Fetch both name and typeOf properties in a single call
        response = self.dc.node.fetch_property_values(
            node_dcids=dcids, properties=["name", "typeOf"]
        )

        result = {}
        for dcid in dcids:
            # Extract name from nodes (name properties have .value attribute)
            name_nodes = response.extract_connected_nodes(dcid, "name")
            # Extract type from DCIDs (typeOf properties have .dcid attribute)
            type_dcids = response.extract_connected_dcids(dcid, "typeOf")

            if name_nodes and type_dcids:
                result[dcid] = NodeInfo(name=name_nodes[0].value, typeOf=type_dcids)

        return result

    async def fetch_entity_types(self, dcids: list[str]) -> dict:
        response = self.dc.node.fetch_property_values(node_dcids=dcids, properties="typeOf")
        return {
            dcid: list(response.extract_connected_dcids(dcid, "typeOf"))
            for dcid in response.get_properties()
        }

    async def search_places(self, names: list[str]) -> dict:
        results_map = {}
        response = self.dc.resolve.fetch_dcids_by_name(names=names)
        data = response.to_dict()
        entities = data.get("entities", [])
        for entity in entities:
            node, candidates = entity.get("node", ""), entity.get("candidates", [])
            if node and candidates:
                results_map[node] = candidates[0].get("dcid", "")
        return results_map

    async def child_place_type_exists(self, parent_place_dcid: str, child_place_type: str) -> bool:
        response = self.dc.node.fetch_place_children(
            place_dcids=parent_place_dcid, children_type=child_place_type, as_dict=True
        )
        return len(response.get(parent_place_dcid, [])) > 0
