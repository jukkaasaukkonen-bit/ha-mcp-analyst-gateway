"""Pure offline-safe analytics on sampled Home Assistant entity states.

Never infers physical causality or financial savings from sparse snapshots.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

COUNTERS = {
    'total': 'counter.heating_optimizer_v1_completed_cycles',
    'normal': 'counter.heating_optimizer_v1_normal_cycles',
    'safety': 'counter.heating_optimizer_v1_safety_interrupted_cycles',
    'short': 'counter.heating_optimizer_v1_short_invalid_cycles',
}
TEMP = ('sensor.koti_room_temperature', 'sensor.bedroom_timmerflotte_temp_hmd_sensor_temperature')
SAVINGS = ('sensor.ivt490_nettosaasto_tanaan', 'sensor.ivt490_nettosaasto_tassa_kuussa', 'sensor.kokonaissaasto_tanaan')


def number(value):
    try:
        n = float(value)
        return n if n == n and abs(n) != float('inf') else None
    except (ValueError, TypeError):
        return None


def analyze(rows, now, interval_minutes=15):
    """rows: iterable (entity, state, ISO timestamp); report conservative evidence."""
    series = defaultdict(list)
    for entity, state, stamp in rows:
        try:
            ts = datetime.fromisoformat(stamp)
            if ts.tzinfo is None or ts > now or ts < now - timedelta(days=90):
                continue
            series[entity].append((ts, state))
        except (TypeError, ValueError):
            continue
    for seq in series.values():
        seq.sort(key=lambda p: p[0])

    def window(days):
        start = now - timedelta(days=days)
        result = {}
        for e, seq in series.items():
            result[e] = [(t, v) for t, v in seq if t >= start]
        return result

    findings = []
    metrics = {}
    for days in (1, 7, 30, 90):
        data = window(days)
        unique = set(t for seq in data.values() for t, _ in seq)
        oldest = min(unique) if unique else None
        # Coverage only when the window has genuinely elapsed since the first sample.
        # The first 24h are always provisional regardless of the sample count.
        elapsed_days = (now - min(t for seq in series.values() for t, _ in seq)).total_seconds() / 86400 if series else 0
        mature = elapsed_days >= days
        expected = max(1, round(days * 24 * 60 / interval_minutes))
        coverage = round(min(100, len(unique) * 100 / expected), 1)
        stats = {'coverage_pct': coverage, 'sample_times': len(unique), 'mature': mature}
        for entity in TEMP:
            values = [number(v) for _, v in data.get(entity, [])]
            values = [v for v in values if v is not None]
            if values:
                stats[entity] = {'min': round(min(values), 2), 'max': round(max(values), 2), 'avg': round(mean(values), 2), 'count': len(values)}
        changes = {}
        for name, entity in COUNTERS.items():
            values = [number(v) for _, v in data.get(entity, [])]
            values = [v for v in values if v is not None]
            if len(values) >= 2:
                monotonic = all(b >= a for a, b in zip(values, values[1:]))
                changes[name] = round(values[-1] - values[0]) if monotonic else None
        stats['cycle_deltas'] = changes
        if changes.get('total') and changes.get('normal') is not None:
            stats['normal_rate_pct'] = round(changes['normal'] / changes['total'] * 100, 1)
        # Financial data are reported as observed point-in-time sensor readings only.
        # Daily/monthly values must never be summed over samples.
        stats['savings_snapshot_eur'] = {e: number(data[e][-1][1]) for e in SAVINGS if data.get(e)}
        metrics[f'{days}d'] = stats

    last7 = metrics['7d']
    changes = last7['cycle_deltas']
    if last7['mature'] and last7['coverage_pct'] >= 75 and (changes.get('total') or 0) >= 5:
        bad = (changes.get('short') or 0) + (changes.get('safety') or 0)
        if bad / changes['total'] >= 0.25:
            findings.append({'id': 'ext-interruptions', 'priority': 'P2', 'finding': 'Frequent non-normal EXT cycles',
                             'evidence': {'bad': bad, 'total': changes['total']}, 'confidence': 'MEDIUM',
                             'action': 'Review stop reasons and controller traces; do not change safety thresholds automatically',
                             'risk': 'Incorrect changes could reduce comfort or disable protections'})
    for e in TEMP:
        val = last7.get(e)
        if val and last7['mature'] and last7['coverage_pct'] >= 75 and val['min'] < 19.5:
            findings.append({'id': 'comfort-low-' + e, 'priority': 'P1', 'finding': 'Observed low indoor temperature',
                             'evidence': val, 'confidence': 'MEDIUM',
                             'action': 'Verify sensor quality and thermal comfort before optimizing further',
                             'risk': 'Potential comfort impact'})
    for e, seq in window(1).items():
        if not seq:
            continue
        invalid = sum(v in ('unknown', 'unavailable') for _, v in seq)
        if len(seq) >= 12 and invalid / len(seq) >= 0.10:
            findings.append({'id': 'availability-' + e, 'priority': 'P2', 'finding': 'Repeated invalid entity readings',
                             'evidence': {'entity': e, 'invalid': invalid, 'samples': len(seq)},
                             'confidence': 'HIGH', 'action': 'Inspect integration and sensor freshness',
                             'risk': 'Data quality may invalidate optimization estimates'})
    hypotheses = []
    if not last7['mature'] or last7['coverage_pct'] < 75:
        hypotheses.append({'id': 'baseline-7d', 'status': 'INSUFFICIENT_DATA',
                           'confidence': 'LOW', 'next_step': 'Collect a complete 7-day sampling window'})
    else:
        hypotheses.append({'id': 'baseline-7d', 'status': 'OBSERVATION_READY',
                           'confidence': 'MEDIUM', 'next_step': 'Compare future weeks before proposing control changes'})
    return {'windows': metrics, 'findings': findings, 'hypotheses': hypotheses,
            'method': 'Sampled state history only. Counters are valid only when monotonic. Savings are snapshots, not verified causal benefits.'}
