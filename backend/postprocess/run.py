#!/usr/bin/env python3
"""postprocess/run.py — CLI DocCore Postprocess"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description="DocCore — Postprocess")
    parser.add_argument("input", help="JSON produit par extraction")
    parser.add_argument("-o", "--output", help="JSON de sortie postprocess")
    parser.add_argument("--csv", help="Export CSV des lignes")
    parser.add_argument("--summary", action="store_true", help="Résumé complet")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs détaillés")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from .pipeline import process

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERREUR] Introuvable: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or (input_path.stem + "_postprocessed.json")
    print(f"\n[Postprocess] {input_path.name}", flush=True)

    t0 = time.perf_counter()
    try:
        invoice = process(input_path, output_path=output_path)
    except Exception as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    if args.summary:
        print(invoice.summary_text())
    else:
        idt = invoice.identity
        fs = invoice.financial_summary
        q = invoice.quality
        print("\n" + "=" * 60)
        print("  DocCore — POSTPROCESS")
        print("=" * 60)
        print(f"  Société      : {idt.company or 'N/A'}")
        print(f"  N° Facture   : {idt.invoice_number or 'N/A'}")
        print(f"  Période      : {idt.period or 'N/A'}  [{idt.period_normalized or '?'}]")
        print(f"  DocuSign     : {idt.docusign_id or 'N/A'}")
        print()
        print(f"  Colonnes     : {invoice.schema.semantics}")
        print()
        for sem, amt in fs.totals_by_column.items():
            print(f"  {sem:<22}: {amt.format(True)}")
        if fs.sharing:
            for party, pct in fs.sharing.items():
                print(f"  {party:<22}: {pct:.1f}%")
            balanced = "✓ OK" if fs.sharing_balanced else "✗ DÉSÉQUILIBRE"
            print(f"  Balance parts : {balanced}")
        if fs.budget_consumed_pct is not None:
            print(f"  Budget conso. : {fs.budget_consumed_pct:.1f}%")
        print()
        print(f"  Sections     : {len(invoice.sections)}")
        print(f"  Lignes       : {q.total_rows} (actives: {q.active_rows})")
        print(f"  Qualité      : {q.overall_score:.0%}")
        if q.issues:
            for i in q.issues:
                print(f"  ✗ {i}")
        if q.warnings:
            for w in q.warnings:
                print(f"  ⚠ {w}")
        print("=" * 60)

    print(f"\n  JSON → {output_path}")
    print(f"  Temps : {elapsed:.3f}s\n")

    if args.csv:
        Path(args.csv).write_text(invoice.to_csv(), encoding="utf-8")
        print(f"  CSV  → {args.csv}\n")

if __name__ == "__main__":
    main()