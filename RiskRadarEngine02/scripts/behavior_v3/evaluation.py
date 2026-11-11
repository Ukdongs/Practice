"""Offline labels/metrics only. This module is never imported by inference."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Event:
    track_id: str
    direction: str
    timestamp_ms: int


def event_metrics(alerts, events, *, exposure_track_hours, lead_window_ms=3000):
    """One-to-one direction/ID matching of alert EPISODE onsets to body-line events.

    Match earliest alert within [event-window,event], inclusive. Exposure is valid
    observed track-hours (not wall-clock hours); callers must exclude censored
    horizons from both alerts and exposure. No true negatives are invented.
    """
    if not math.isfinite(exposure_track_hours) or exposure_track_hours <= 0 or lead_window_ms <= 0:
        raise ValueError('Positive exposure and lead window required')
    alerts, events = list(alerts), list(events)
    used, leads = set(), []
    for event in sorted(events, key=lambda e: e.timestamp_ms):
        candidates = [(a.timestamp_ms, i) for i, a in enumerate(alerts) if i not in used
                      and a.track_id == event.track_id and a.direction == event.direction
                      and 0 <= event.timestamp_ms-a.timestamp_ms <= lead_window_ms]
        if candidates:
            _, i = min(candidates)
            used.add(i)
            leads.append((event.timestamp_ms-alerts[i].timestamp_ms)/1000)
    tp, fp, fn = len(used), len(alerts)-len(used), len(events)-len(used)
    return {'true_positive_events': tp, 'false_alert_episodes': fp, 'missed_events': fn,
            'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None,
            'miss_rate': fn/(tp+fn) if tp+fn else None,
            'false_alerts_per_track_hour': fp/exposure_track_hours,
            'lead_time_s': leads, 'mean_lead_time_s': sum(leads)/tp if tp else None,
            'exposure_track_hours': exposure_track_hours,
            'lead_window_ms': lead_window_ms}


@dataclass(frozen=True)
class Window:
    site: str
    recording: str
    driver: str
    start_ms: int
    end_ms: int
    split: str


def validate_holdout(windows, *, embargo_ms=0):
    """Fail closed: caller assigns splits BEFORE feature fitting/window creation.

    A site, recording OR known driver may occur in only one partition. Even
    same-partition windows cannot overlap in a recording. Train must precede
    validation, then test in the supplied common absolute timestamp domain.
    Unknown drivers prevent claiming a driver-disjoint result.
    """
    windows = list(windows)
    if embargo_ms < 0 or not windows:
        raise ValueError('Nonempty windows and nonnegative embargo required')
    seen = {}
    ranks = {'train': 0, 'validation': 1, 'test': 2}
    for w in windows:
        if (w.split not in ranks or not all((w.site, w.recording, w.driver))
                or w.driver == 'UNKNOWN' or w.start_ms >= w.end_ms):
            raise ValueError('Invalid window or unknown driver; holdout blocked')
        for key in (('site', w.site), ('recording', w.site, w.recording), ('driver', w.driver)):
            if key in seen and seen[key] != w.split:
                raise ValueError('Group leakage: '+repr(key))
            seen[key] = w.split
    for i, a in enumerate(windows):
        for b in windows[i+1:]:
            if (a.site, a.recording) == (b.site, b.recording):
                if max(a.start_ms, b.start_ms) < min(a.end_ms, b.end_ms)+embargo_ms:
                    raise ValueError('Overlapping windows or embargo violation')
            if ranks[a.split] < ranks[b.split] and a.end_ms+embargo_ms > b.start_ms:
                raise ValueError('Non-temporal holdout')
            if ranks[b.split] < ranks[a.split] and b.end_ms+embargo_ms > a.start_ms:
                raise ValueError('Non-temporal holdout')
    return {'status': 'PASS', 'windows': len(windows), 'normalization': 'none',
            'driver_identity': 'caller must verify; local track ID is not driver ID'}


def temporal_holdout(windows, *, train_end_ms, validation_end_ms, embargo_ms=0):
    """Assign whole windows before any fitting; reject boundary-straddling groups.

    Input Window.split is ignored. No random shuffling and no normalization.
    Caller supplies verified group identities and common absolute timestamps.
    """
    from dataclasses import replace
    if train_end_ms >= validation_end_ms or embargo_ms < 0:
        raise ValueError('Invalid temporal boundaries')
    result = []
    for w in windows:
        if w.end_ms <= train_end_ms:
            split = 'train'
        elif w.start_ms >= train_end_ms+embargo_ms and w.end_ms <= validation_end_ms:
            split = 'validation'
        elif w.start_ms >= validation_end_ms+embargo_ms:
            split = 'test'
        else:
            raise ValueError('Window straddles a split or embargo boundary')
        result.append(replace(w, split=split))
    validate_holdout(result, embargo_ms=embargo_ms)
    return result


def require_physical_pass(scene):
    """Reuse unmodified V2 gate; ANY discovered observed collision is fatal."""
    from scripts.sim_v2.qa import audit
    result = audit(scene)
    if result['collisions'] or result['status'] != 'PASS':
        raise ValueError('Physical QA FAIL: '+repr(result['failures']))
    return result
