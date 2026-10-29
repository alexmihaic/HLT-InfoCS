"""Offline batch projection: the BDNS Python policy is the sole URL authority."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from infocs.fetch.bdns.enrichment import clickable_bdns_regulatory_bases_url, valid_bdns_supplied_url


def project(items):
    result = []
    for item in items:
        bases, office = item['bases'], item['office']
        result.append({
            'bases': clickable_bdns_regulatory_bases_url(bases) if isinstance(bases, str) else None,
            'office': office if isinstance(office, str) and valid_bdns_supplied_url(office) else None,
        })
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(project(json.load(sys.stdin)), ensure_ascii=True, separators=(',', ':')))
    except Exception:
        print('BDNS link projection failed', file=sys.stderr)
        sys.exit(1)
