#!/usr/bin/env python3
"""Convertit un classeur outputAll (.xlsx) en base compacte (.npz) pour l'application ADV Propulse."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from adv_propulse_scaling_optimizer import export_compact_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path, help="Classeur outputAll complet (Summary + feuilles run.*)")
    parser.add_argument("output", type=Path, nargs="?", help="Base compacte a ecrire (defaut : meme nom en .npz)")
    parser.add_argument(
        "--ref-blade-length-m",
        type=float,
        default=None,
        help="Envergure de pale du post-traitement (defaut : lue dans le nom du fichier, ex. _Lpale0.375m)",
    )
    args = parser.parse_args()

    span = args.ref_blade_length_m
    if span is None:
        match = re.search(r"Lpale([0-9]+(?:[.,][0-9]+)?)m", args.xlsx.name)
        span = float(match.group(1).replace(",", ".")) if match else None
    output = args.output or args.xlsx.with_suffix(".npz")
    meta = export_compact_database(args.xlsx, output, ref_blade_length_m=span)
    print(f"{output} : {output.stat().st_size / 1e6:.1f} Mo (source {args.xlsx.stat().st_size / 1e6:.1f} Mo)")
    print(meta)


if __name__ == "__main__":
    main()
