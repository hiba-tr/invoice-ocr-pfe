"""
postprocess/models.py
=====================
Modèles de données génériques du postprocess DocCore.
"""
from __future__ import annotations
import csv
import io
import json
from dataclasses import dataclass, field, asdict
from typing import  Dict, List, Optional
import re
from pathlib import Path

@dataclass
class MonetaryAmount:
    raw: str
    value: Optional[float]
    currency: str = "USD"
    is_negative: bool = False
    is_empty: bool = False

    @classmethod
    def from_text(cls, text: str, currency: str = "USD") -> "MonetaryAmount":
        t = (text or "").strip()
        t = re.sub(r'[€$£C\u00a0\u202f]', '', t, flags=re.IGNORECASE).strip()
        if not t or t in ("-", "—", "N/A", "n/a", "- ", ""):
            return cls(raw=t or "-", value=None, currency=currency, is_empty=True)
        negative = t.startswith("(") and t.endswith(")")
        clean = t.strip("()")
        clean = re.sub(r"\s*[A-Za-z€£$]{1,3}\s*$", "", clean).strip() or clean
        clean = clean.replace("'", "")
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean and "." not in clean:
            parts = clean.split(",")
            if len(parts[-1]) <= 2:
                clean = clean.replace(" ", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        else:
            clean = clean.replace(" ", "")
        try:
            val = float(clean)
            if negative:
                val = -abs(val)
            is_neg = val < 0 or (negative and val == 0.0)
            return cls(raw=t, value=val, currency=currency, is_negative=is_neg, is_empty=False)
        except ValueError:
            return cls(raw=t, value=None, currency=currency)

    def format(self, show_currency: bool = False) -> str:
        if self.is_empty or self.value is None:
            return "-"
        suffix = f" {self.currency}" if show_currency else ""
        if self.is_negative:
            return f"({abs(self.value):,.2f}){suffix}"
        return f"{self.value:,.2f}{suffix}"

    def to_dict(self) -> Dict:
        return {"raw": self.raw, "value": self.value, "currency": self.currency,
                "is_negative": self.is_negative, "is_empty": self.is_empty}

@dataclass
class ColumnDef:
    index: int
    header_raw: str
    semantic: str
    data_type: str = "amount"
    currency: str = "USD"

    @property
    def is_numeric(self) -> bool:
        return self.data_type in ("amount", "quantity")

@dataclass
class RawTable:
    table_id: str
    headers: List[str]
    rows: List[List[str]]

@dataclass
class TableSchema:
    columns: List[ColumnDef] = field(default_factory=list)

    @property
    def description_col(self) -> Optional[ColumnDef]:
        for c in self.columns:
            if not c.is_numeric or "description" in c.semantic.lower():
                return c
        return self.columns[0] if self.columns else None

    @property
    def numeric_cols(self) -> List[ColumnDef]:
        return [c for c in self.columns if c.is_numeric]

    @property
    def headers_display(self) -> List[str]:
        return [c.header_raw for c in self.columns]

    @property
    def semantics(self) -> List[str]:
        return [c.semantic for c in self.columns]

    def get_col_by_semantic(self, semantic: str) -> Optional[ColumnDef]:
        for c in self.columns:
            if c.semantic == semantic:
                return c
        return None

    def to_dict(self) -> Dict:
        return {
            "columns": [asdict(c) for c in self.columns],
            "headers": self.headers_display,
            "semantics": self.semantics,
        }

@dataclass
class LineItem:
    description: str
    row_index: int
    row_type: str  # data, total, subtotal, section_header
    values: Dict[str, MonetaryAmount] = field(default_factory=dict)
    quality_flags: List[str] = field(default_factory=list)
    source_page: int = 1

    @property
    def has_activity(self) -> bool:
        return any(v.value is not None for v in self.values.values())

    def get_value(self, semantic: str) -> Optional[MonetaryAmount]:
        return self.values.get(semantic)

    def get_numeric_values(self) -> Dict[str, float]:
        return {k: v.value for k, v in self.values.items() if v.value is not None}

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "row_index": self.row_index,
            "row_type": self.row_type,
            "amounts": {k: v.to_dict() for k, v in self.values.items()},
            "is_active": self.has_activity,
            "quality_flags": self.quality_flags,
        }

@dataclass
class Section:
    name: str
    row_index: int = 0
    items: List[LineItem] = field(default_factory=list)
    subtotal_declared: Optional[Dict[str, MonetaryAmount]] = None
    subtotal_calculated: Optional[Dict[str, MonetaryAmount]] = None
    columns_schema: Optional[Dict] = None 
    @property
    def active_items(self) -> List[LineItem]:
        return [i for i in self.items if i.has_activity]

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def active_count(self) -> int:
        return len(self.active_items)

    def to_dict(self) -> Dict:
        def _fmt_subtotal(st):
            if st is None:
                return None
            return {k: v.to_dict() for k, v in st.items()}
        d = {
            "name": self.name,
            "row_index": self.row_index,
            "item_count": self.item_count,
            "active_item_count": self.active_count,
            "items": [i.to_dict() for i in self.items],
            "subtotal_calculated": _fmt_subtotal(self.subtotal_calculated),
            "subtotal_declared": _fmt_subtotal(self.subtotal_declared),
        }
        if self.columns_schema:
            d["columns"] = self.columns_schema
        return d

@dataclass
class FinancialSummary:
    total_rows: List[LineItem] = field(default_factory=list)
    totals_by_column: Dict[str, MonetaryAmount] = field(default_factory=dict)
    sharing: Dict[str, float] = field(default_factory=dict)
    sharing_balanced: Optional[bool] = None
    budget_consumed_pct: Optional[float] = None
    ytd_vs_budget_variance: Optional[float] = None
    anomalies: List[str] = field(default_factory=list)

    def get_total(self, semantic: str) -> Optional[MonetaryAmount]:
        return self.totals_by_column.get(semantic)

    def to_dict(self) -> Dict:
        return {
            "totals_by_column": {k: v.to_dict() for k, v in self.totals_by_column.items()},
            "sharing": self.sharing,
            "sharing_balanced": self.sharing_balanced,
            "budget_consumed_pct": self.budget_consumed_pct,
            "ytd_vs_budget_variance": self.ytd_vs_budget_variance,
            "total_rows": [r.to_dict() for r in self.total_rows],
            "anomalies": self.anomalies,
        }

@dataclass
class DocumentIdentity:
    company: Optional[str] = None
    concession: Optional[str] = None
    document_type: Optional[str] = None
    period: Optional[str] = None
    period_normalized: Optional[str] = None
    docusign_id: Optional[str] = None
    total_pages: Optional[int] = None
    pages_processed: int = 0
    source_file: Optional[str] = None
    document_hash: Optional[str] = None
    extraction_status: str = "unknown"
    currency: str = "USD"
    invoice_number: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class ExtractionQuality:
    overall_score: float = 0.0
    identity_complete: bool = False
    tables_found: int = 0
    total_rows: int = 0
    active_rows: int = 0
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class InvoiceDocument:
    identity: DocumentIdentity
    schema: TableSchema
    sections: List[Section]
    financial_summary: FinancialSummary
    quality: ExtractionQuality
    raw_tables: List[RawTable] = field(default_factory=list)
    extra_metadata: Dict[str, str] = field(default_factory=dict)
    candidate_texts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "identity": self.identity.to_dict(),
            "columns": self.schema.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "financial_summary": self.financial_summary.to_dict(),
            "quality": self.quality.to_dict(),
            "raw_tables": [{"table_id": rt.table_id, "headers": rt.headers, "rows": rt.rows} for rt in self.raw_tables],
            "extra_metadata": self.extra_metadata, 
            "candidate_texts": self.candidate_texts,
        }

    def to_json(self, path: Optional[str] = None, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)
        if path:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def to_csv(self) -> str:
        out = io.StringIO()
        w = csv.writer(out)
        semantics = self.schema.semantics
        w.writerow(["section", "description", "row_type"] + semantics)
        for section in self.sections:
            for item in section.items:
                row = [section.name, item.description, item.row_type]
                for sem in semantics:
                    amt = item.get_value(sem)
                    row.append(amt.value if amt else None)
                w.writerow(row)
        return out.getvalue()

    def to_formatted_table(self, max_col_width: int = 30) -> str:
        """
        Génère un tableau formaté en texte, reproduisant au mieux l'original.
        """
        headers = self.schema.headers_display
        # Collecter toutes les lignes
        rows = []
        for section in self.sections:
            for item in section.items:
                row = []
                for col in self.schema.columns:
                    amt = item.values.get(col.semantic)
                    if amt:
                        row.append(amt.format() if col.is_numeric else item.description if col.semantic == "description" else amt.raw)
                    else:
                        row.append("")
                rows.append(row)
        # Calculer les largeurs de colonnes
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        # Limiter la largeur
        col_widths = [min(w, max_col_width) for w in col_widths]
        def format_row(cells):
            parts = []
            for i, cell in enumerate(cells):
                parts.append(str(cell).ljust(col_widths[i])[:col_widths[i]])
            return " | ".join(parts)
        lines = []
        lines.append(format_row(headers))
        lines.append("-+-".join("-" * w for w in col_widths))
        for row in rows:
            lines.append(format_row(row))
        return "\n".join(lines)

    def summary_text(self) -> str:
        idt = self.identity
        fs = self.financial_summary
        q = self.quality
        lines = ["=" * 60, "  INVOICE DOCUMENT — POST-PROCESSED SUMMARY", "=" * 60,
                  f"  Company      : {idt.company or 'N/A'}",
                  f"  Invoice N°   : {idt.invoice_number or 'N/A'}",
                  f"  Type         : {idt.document_type or 'N/A'}",
                  f"  Period       : {idt.period or 'N/A'}  [{idt.period_normalized or '?'}]",
                  f"  DocuSign     : {idt.docusign_id or 'N/A'}",
                  f"  Pages        : {idt.pages_processed} / {idt.total_pages or '?'}",
                  "", "  COLONNES DÉTECTÉES", "  " + "-" * 40]
        for col in self.schema.columns:
            lines.append(f"  [{col.index}] {col.semantic:<20} ← \"{col.header_raw}\"")
        lines += ["", "  TOTAUX", "  " + "-" * 40]
        for sem, amt in fs.totals_by_column.items():
            lines.append(f"  {sem:<22}: {amt.format(True)}")
        if fs.sharing:
            lines += ["", "  PARTAGES", "  " + "-" * 40]
            for party, pct in fs.sharing.items():
                lines.append(f"  {party:<22}: {pct:.1f}%")
            balanced = "✓ OK" if fs.sharing_balanced else "✗ ANOMALIE"
            lines.append(f"  Balance         : {balanced}")
        if fs.budget_consumed_pct is not None:
            lines.append(f"  Budget consommé : {fs.budget_consumed_pct:.1f}%")
        lines += ["", "  SECTIONS", "  " + "-" * 40]
        for s in self.sections:
            lines.append(f"  ▸ {s.name}  [{s.active_count}/{s.item_count} actives]")
        lines += ["", "  QUALITÉ", "  " + "-" * 40,
                  f"  Score global    : {q.overall_score:.0%}"]
        for issue in q.issues:
            lines.append(f"  ✗ {issue}")
        for w in q.warnings:
            lines.append(f"  ⚠ {w}")
        if fs.anomalies:
            lines += ["", "  ANOMALIES FINANCIÈRES", "  " + "-" * 40]
            for a in fs.anomalies:
                lines.append(f"  ! {a}")
        lines.append("=" * 60)
        return "\n".join(lines)