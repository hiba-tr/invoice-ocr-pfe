from __future__ import annotations
from typing import Any, List, Optional, Dict

class BBox:
    __slots__ = ("l", "t", "r", "b")
    def __init__(self, l: float, t: float, r: float, b: float):
        self.l, self.t, self.r, self.b = l, t, r, b
    @property
    def cx(self) -> float:
        return (self.l + self.r) / 2
    @property
    def cy(self) -> float:
        return (self.t + self.b) / 2
    @property
    def width(self) -> float:
        return self.r - self.l
    @property
    def height(self) -> float:
        return self.b - self.t
    def horizontal_overlap(self, other: "BBox") -> float:
        intersection = max(0.0, min(self.r, other.r) - max(self.l, other.l))
        return intersection / max(self.width, 1e-6)
    def to_dict(self) -> Dict[str, float]:
        return {"l": self.l, "t": self.t, "r": self.r, "b": self.b}
    @classmethod
    def from_cell(cls, cell: Any) -> Optional["BBox"]:
        if hasattr(cell, "bbox") and cell.bbox:
            b = cell.bbox
            return cls(b.l, b.t, b.r, b.b)
        if hasattr(cell, "rect") and cell.rect:
            r = cell.rect
            xs = [r.r_x0, r.r_x1, r.r_x2, r.r_x3]
            ys = [r.r_y0, r.r_y1, r.r_y2, r.r_y3]
            return cls(min(xs), min(ys), max(xs), max(ys))
        if isinstance(cell, dict):
            b = cell.get("bbox") or {}
            if b:
                return cls(b.get("l", 0), b.get("t", 0), b.get("r", 0), b.get("b", 0))
        return None
    @classmethod
    def from_dict(cls, d: Dict) -> Optional["BBox"]:
        if not d:
            return None
        return cls(d.get("l", 0), d.get("t", 0), d.get("r", 0), d.get("b", 0))

def sort_cells_spatially(cells: List[Any]) -> List[Any]:
    def get_cy(c):
        b = BBox.from_cell(c)
        return b.cy if b else 0.0
    def get_cx(c):
        b = BBox.from_cell(c)
        return b.cx if b else 0.0
    return sorted(cells, key=lambda c: (round(get_cy(c) / 3), get_cx(c)))