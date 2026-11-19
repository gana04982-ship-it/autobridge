"""
AutoBridge - Hierarchical Level (HL) Tree Builder & Graph Topology Validator
Transforms flat ANSI X12 856 HL segments into a validated, stateful object tree.

In ANSI X12 856 (Advance Ship Notice / Manifest):
  HL*1**S~    (Shipment)
  HL*2*1*O~   (Order)
  HL*3*2*T~   (Tare / Pallet)
  HL*4*3*P~   (Pack / Box)
  HL*5*4*I~   (Item / Part)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from autobridge.core.lexer import X12Segment


@dataclass
class HLViolation:
    code: str                   # E.g. "HL_ORPHAN_PARENT", "HL_DUPLICATE_ID"
    severity: str               # "CRITICAL", "ERROR", "WARNING"
    line_number: int
    hl_id: str
    message: str
    fix_recommendation: str


@dataclass
class HLNode:
    hl_id: int                  # HL01 (1, 2, 3...)
    parent_id: Optional[int]    # HL02 (None for root)
    level_code: str             # HL03 ('S', 'O', 'T', 'P', 'I')
    hl_segment: X12Segment      # The HL segment itself
    segments: List[X12Segment] = field(default_factory=list) # Segments scoped to this node
    children: List['HLNode'] = field(default_factory=list)
    parent: Optional['HLNode'] = None

    def get_segment(self, tag: str) -> Optional[X12Segment]:
        """Returns the first segment matching tag scoped directly under this HL node."""
        for seg in self.segments:
            if seg.tag == tag:
                return seg
        return None

    def get_segments(self, tag: str) -> List[X12Segment]:
        """Returns all segments matching tag scoped directly under this HL node."""
        return [s for s in self.segments if s.tag == tag]

    def find_descendants_by_level(self, level_code: str) -> List['HLNode']:
        """Recursively collects all descendant nodes of a specific level code (e.g. all 'I' items)."""
        results = []
        for child in self.children:
            if child.level_code == level_code:
                results.append(child)
            results.extend(child.find_descendants_by_level(level_code))
        return results

    def __repr__(self) -> str:
        return f"<HLNode [{self.level_code}] ID:{self.hl_id} Parent:{self.parent_id} Children:{len(self.children)} Segments:{len(self.segments)}>"


@dataclass
class HLTree:
    root: Optional[HLNode]
    nodes: Dict[int, HLNode]
    violations: List[HLViolation]

    def get_shipment(self) -> Optional[HLNode]:
        """Returns root shipment level node."""
        return self.root if (self.root and self.root.level_code == 'S') else None

    def get_all_orders(self) -> List[HLNode]:
        return [n for n in self.nodes.values() if n.level_code == 'O']

    def get_all_pallets(self) -> List[HLNode]:
        return [n for n in self.nodes.values() if n.level_code == 'T']

    def get_all_packs(self) -> List[HLNode]:
        return [n for n in self.nodes.values() if n.level_code == 'P']

    def get_all_items(self) -> List[HLNode]:
        return [n for n in self.nodes.values() if n.level_code == 'I']


def build_hl_tree(tx_segments: List[X12Segment]) -> HLTree:
    """
    Parses a transaction set's segments into a validated hierarchical tree.
    Performs topological graph validation on parent-child pointers.
    """
    violations: List[HLViolation] = []
    nodes: Dict[int, HLNode] = {}
    current_node: Optional[HLNode] = None
    root_node: Optional[HLNode] = None

    expected_next_id = 1

    for seg in tx_segments:
        if seg.tag == "HL":
            # Extract HL elements:
            # HL01: Hierarchical ID Number (mandatory integer)
            # HL02: Hierarchical Parent ID Number (mandatory except root)
            # HL03: Hierarchical Level Code (mandatory: S, O, T, P, I)
            raw_id = seg.get(1)
            raw_parent = seg.get(2)
            level = seg.get(3).upper()

            # 1. Validate HL01 integer
            try:
                hl_id = int(raw_id)
            except ValueError:
                violations.append(
                    HLViolation(
                        code="HL_INVALID_ID_NUMBER",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        hl_id=raw_id,
                        message=f"HL01 '{raw_id}' is not a valid integer.",
                        fix_recommendation="Ensure HL01 is an integer starting from 1."
                    )
                )
                continue

            # 2. Check for duplicate HL01
            if hl_id in nodes:
                violations.append(
                    HLViolation(
                        code="HL_DUPLICATE_ID",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        hl_id=str(hl_id),
                        message=f"Duplicate HL01 identifier '{hl_id}'. Each HL segment must have a unique ID.",
                        fix_recommendation=f"Renumber HL segments sequentially (expected ID {expected_next_id})."
                    )
                )
                continue

            # 3. Check sequential ordering recommendation
            if hl_id != expected_next_id:
                violations.append(
                    HLViolation(
                        code="HL_NON_SEQUENTIAL_ID",
                        severity="WARNING",
                        line_number=seg.line_number,
                        hl_id=str(hl_id),
                        message=f"HL01 '{hl_id}' is not strictly sequential (expected {expected_next_id}).",
                        fix_recommendation=f"Number HL segments sequentially starting at 1."
                    )
                )
            expected_next_id = hl_id + 1

            # 4. Validate Level Code (HL03)
            valid_levels = {'S', 'O', 'T', 'P', 'I'}
            if level not in valid_levels:
                violations.append(
                    HLViolation(
                        code="HL_INVALID_LEVEL_CODE",
                        severity="CRITICAL",
                        line_number=seg.line_number,
                        hl_id=str(hl_id),
                        message=f"Invalid HL03 level code '{level}'. Expected one of {valid_levels}.",
                        fix_recommendation="Set HL03 to valid level code: S (Shipment), O (Order), T (Tare), P (Pack), I (Item)."
                    )
                )

            # 5. Parse Parent ID (HL02)
            parent_id: Optional[int] = None
            if raw_parent:
                try:
                    parent_id = int(raw_parent)
                except ValueError:
                    violations.append(
                        HLViolation(
                            code="HL_INVALID_PARENT_NUMBER",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            hl_id=str(hl_id),
                            message=f"HL02 parent ID '{raw_parent}' is not a valid integer.",
                            fix_recommendation="Ensure HL02 references a valid integer parent ID."
                        )
                    )

            # 6. Graph Topology Rules
            if parent_id is None:
                # Root node
                if root_node is not None:
                    violations.append(
                        HLViolation(
                            code="HL_MULTIPLE_ROOTS",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            hl_id=str(hl_id),
                            message=f"Multiple root HL segments detected. Prior root was ID '{root_node.hl_id}'.",
                            fix_recommendation="An Advance Ship Notice must have exactly one root Shipment (S) level."
                        )
                    )
                if level != 'S':
                    violations.append(
                        HLViolation(
                            code="HL_ROOT_NOT_SHIPMENT",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            hl_id=str(hl_id),
                            message=f"Root HL node (without parent) must have level code 'S' (Shipment). Found '{level}'.",
                            fix_recommendation="Set root HL03 to 'S'."
                        )
                    )
                new_node = HLNode(
                    hl_id=hl_id,
                    parent_id=None,
                    level_code=level,
                    hl_segment=seg
                )
                nodes[hl_id] = new_node
                if root_node is None:
                    root_node = new_node
                current_node = new_node

            else:
                # Child node: Verify parent exists
                if parent_id not in nodes:
                    violations.append(
                        HLViolation(
                            code="HL_ORPHAN_PARENT",
                            severity="CRITICAL",
                            line_number=seg.line_number,
                            hl_id=str(hl_id),
                            message=f"Parent ID '{parent_id}' referenced in HL02 does not exist or appears after this segment.",
                            fix_recommendation=f"Ensure parent node '{parent_id}' is defined prior to child '{hl_id}'."
                        )
                    )
                    parent_node = None
                else:
                    parent_node = nodes[parent_id]

                new_node = HLNode(
                    hl_id=hl_id,
                    parent_id=parent_id,
                    level_code=level,
                    hl_segment=seg,
                    parent=parent_node
                )
                nodes[hl_id] = new_node
                if parent_node:
                    parent_node.children.append(new_node)
                current_node = new_node

        else:
            # Non-HL segment: Attaches to the active HL scope if an HL has been opened
            if current_node is not None:
                current_node.segments.append(seg)

    return HLTree(
        root=root_node,
        nodes=nodes,
        violations=violations
    )
