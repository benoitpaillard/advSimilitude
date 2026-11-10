"""Package the audited campaign summaries; no remote access or CFD rerun required."""
from pathlib import Path
import argparse
import hashlib
import json

import pandas as pd


def build(analysis: Path, destination: Path) -> None:
    records = []
    sources = []
    for host in ['jony3', 'jony4']:
        path = analysis / f'{host}-summaries.json'
        content = path.read_bytes()
        sources.append({'file': path.name, 'sha256': hashlib.sha256(content).hexdigest()})
        for row in json.loads(content):
            records.append({
                'variant': row['variant'], 'run': row['run'],
                'converged': row['converged'], 'diverged': row['diverged'],
                **row['summary'],
            })
    df = pd.DataFrame(records).drop_duplicates(['variant', 'run']).sort_values(['variant', 'Ve [m/s]', 'Lambda [-]', 'Bmax[°]'])
    df.to_csv(destination / 'campaign_results.csv', index=False)
    metadata = {
        'campaign': 'gaetan-20261022', 'analysis_date': '2026-11-10',
        'geometry': {'D_m': 0.3, 'blade_length_m': 0.375, 'blades': 3, 'CoR_percent': 33},
        'source_snapshots': sources,
        'reference_database': 'adv_propulse_database_Lpale0.375m.npz',
        'reference_sha256': hashlib.sha256((destination / 'adv_propulse_database_Lpale0.375m.npz').read_bytes()).hexdigest(),
        'results_sha256': hashlib.sha256((destination / 'campaign_results.csv').read_bytes()).hexdigest(),
        'unique_cases': len(df),
        'converged_cases': int(df.converged.sum()),
        'excluded_anomalies': [
            'dir_plus2/run.309', 'combined_1p7/run.151',
            'combined_1p7/run.1084', 'sigma_1p7/run.1102',
        ],
        'validation_V10_to_V30': {
            'method': 'Same lambda/Bmax, converged at both V=10 and V=30; absolute relative errors.',
            'sigma_1p7': {'n': 10, 'thrust_median_pct': 1.03, 'thrust_max_pct': 3.26, 'DHP_median_pct': 0.73, 'DHP_max_pct': 2.62, 'Mh_median_pct': 1.25, 'Mh_max_pct': 3.45},
            'combined_1p7': {'n': 9, 'thrust_median_pct': 2.45, 'thrust_max_pct': 5.83, 'DHP_median_pct': 2.10, 'DHP_max_pct': 4.94, 'Mh_median_pct': 1.78, 'Mh_max_pct': 6.84},
        },
        'limitations': [
            'Convergence marker checks periodic Mz, not mesh independence or all force peaks.',
            'Reference pilot: thrust -0.86%, DHP -0.08%, Mh max +20.0%.',
            'V=30 checks do not validate lambda=0.5 or lambda=1.7/Bmax=25.',
            'No validated campaign time series are bundled.',
        ],
    }
    (destination / 'campaign_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis', type=Path)
    args = parser.parse_args()
    build(args.analysis, Path(__file__).resolve().parent)
