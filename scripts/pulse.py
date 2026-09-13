#!/usr/bin/env python3
"""Fetch SEISMOGRAPH model weather, append history, emit a same-origin snapshot.

Runs on GitHub Actions cron. Pure stdlib: no install step, no secrets, no
LLM calls. The browser cannot call the gateway directly (it sends no
Access-Control-Allow-Origin header), so this job is the bridge: it publishes
data/weather.json next to index.html, where fetch() is same-origin.

Every number the site renders is computed here from real gateway output.
Where there is not yet enough history to compute something honestly, this
emits state "unknown" rather than a fabricated value.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from datetime import datetime, timezone

SOURCE = os.environ.get(
    "SG_WEATHER_URL",
    "https://seismograph-weather.onrender.com/v1/weather",
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history.jsonl"
SNAPSHOT = DATA / "weather.json"

# Mirrors gateway.main.STALE_AFTER_HOURS (DASH-3). A leg quieter than
# this publishes STALE, never STABLE.
STALE_AFTER_HOURS = 30.0

# CUSUM constants as used in the published backtest: one-sided lower
# CUSUM in sigma units, k = 0.5 slack, h = 5.0 decision interval.
CUSUM_K = 0.5
CUSUM_H = 5.0

# Points of history required before a baseline is deep enough to derive
# a z-score or a CUSUM trace from.
MIN_BASELINE = 8
BASELINE_WINDOW = 20
MAX_HISTORY = 2000

# Render's free tier sleeps; a cold start can take ~30s.
TIMEOUT = 90


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str) -> list:
    req = urllib.request.Request(
        url, headers={"User-Agent": "driftdefense-pulse/1.0"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("expected a JSON array from /v1/weather")
    return payload


def read_history() -> list:
    if not HISTORY.exists():
        return []
    rows = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def mean(xs: list) -> float:
    return sum(xs) / len(xs)


def stdev(xs: list, mu: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return var ** 0.5


def cusum_lower(series: list, mu0: float, sigma0: float) -> list:
    """One-sided lower CUSUM in sigma units.

    S_t = max(0, S_{t-1} + (mu0 - x_t)/sigma0 - k). Detects downward
    shifts -- a JSON success rate sagging below its own baseline. This
    is the same recurrence, with the same k and h, as the published
    backtest in the SEISMOGRAPH repo.
    """
    s = 0.0
    trace = []
    for x in series:
        s = max(0.0, s + (mu0 - x) / sigma0 - CUSUM_K)
        trace.append(round(s, 4))
    return trace


def analyse(model, history: list, current: dict) -> dict:
    """Derive the published indicators for one model leg."""
    rates = [
        h["json_success_rate"]
        for h in history
        if h.get("model_tuple") == model
        and isinstance(h.get("json_success_rate"), (int, float))
    ]

    age = current.get("window_age_hours")
    rate = current.get("json_success_rate")
    length = current.get("avg_output_length")
    depth = current.get("sample_count") or 0

    # The page plots this directly. With two observations it draws two
    # points; the trace densifies on its own as the cron accumulates.
    series = [
        {
            "t": h.get("t"),
            "rate": h.get("json_success_rate"),
            "age": h.get("window_age_hours"),
        }
        for h in history
        if h.get("model_tuple") == model
        and isinstance(h.get("json_success_rate"), (int, float))
    ][-40:]

    out = {
        "model_tuple": model,
        "series": series,
        "status": current.get("status"),
        "window_age_hours": age,
        "json_success_rate": rate,
        "avg_output_length": length,
        "sample_count": depth,
        "last_alert_timestamp": current.get("last_alert_timestamp"),
        "window_end": current.get("window_end"),
        "history_points": len(rates),
        "baseline_required": MIN_BASELINE,
        "cusum_h": CUSUM_H,
    }

    # The baseline is built from this site's own accumulated
    # observations, so it sharpens with every run. Until it is deep
    # enough to mean anything, say so rather than publish a number.
    if len(rates) >= MIN_BASELINE and rate is not None:
        base = rates[-BASELINE_WINDOW:]
        mu0 = mean(base)
        # A degenerate sigma would make z explode; floor it below the
        # observed noise of a healthy leg.
        sigma0 = max(stdev(base, mu0), 1e-4)
        trace = cusum_lower(base, mu0, sigma0)
        s_now = trace[-1]
        out["calibrated"] = True
        out["mu0"] = round(mu0, 6)
        out["sigma0"] = round(sigma0, 6)
        out["z"] = round((rate - mu0) / sigma0, 2)
        out["cusum"] = s_now
        out["cusum_pct"] = round(min(s_now / CUSUM_H, 1.0) * 100, 1)
        out["cusum_trace"] = trace[-24:]
    else:
        out["calibrated"] = False
        out["cusum_trace"] = []

    # --- the six checks the hexagram renders -------------------------
    # Each is strictly yes / no / unknown. "unknown" is never rounded up
    # into "yes": a monitoring product that guesses green is committing
    # the exact failure it exists to catch.
    # The gateway's own published status is authoritative here, not a
    # threshold copied into this file. STALE_AFTER_HOURS is upstream's
    # constant; hardcoding it would mean that the day upstream retunes
    # it, this board silently disagrees with the system it reports on --
    # a silent behavioural change in a dependency, which is precisely
    # the failure this project exists to detect. Mirroring it here would
    # be the bug wearing the product's own uniform.
    #
    # The local threshold is kept only to CHECK upstream, never to
    # overrule it: if the two verdicts diverge, that divergence is
    # itself a finding and gets published rather than smoothed over.
    status = current.get("status")
    if status == "STALE":
        reporting = "no"
    elif status in ("STABLE", "DRIFTING"):
        reporting = "yes"
    else:
        reporting = "unknown"

    if isinstance(age, (int, float)) and status in ("STABLE", "DRIFTING", "STALE"):
        local = "no" if age > STALE_AFTER_HOURS else "yes"
        if local != reporting:
            out["threshold_divergence"] = {
                "gateway_status": status,
                "local_threshold_hours": STALE_AFTER_HOURS,
                "window_age_hours": age,
                "note": "gateway verdict and this board's local threshold "
                        "disagree; the gateway is authoritative and its "
                        "freshness rule has probably changed",
            }

    depth_ok = "yes" if depth >= MIN_BASELINE else "no"
    alert_free = "no" if current.get("last_alert_timestamp") else "yes"
    length_ok = "yes" if length else "unknown"

    if out["calibrated"]:
        in_band = "yes" if abs(out["z"]) <= 3.0 else "no"
        below_h = "yes" if out["cusum"] < CUSUM_H else "no"
        band_detail = "z = " + str(out["z"]) + " sigma from baseline"
        cusum_detail = "S- " + str(out["cusum"]) + " / h " + str(CUSUM_H)
    else:
        in_band = "unknown"
        below_h = "unknown"
        forming = "baseline forming - " + str(len(rates)) + "/" + str(MIN_BASELINE) + " points"
        band_detail = forming
        cusum_detail = forming

    age_detail = (
        "window age " + format(age, ".1f") + "h vs " + format(STALE_AFTER_HOURS, ".0f") + "h threshold"
        if isinstance(age, (int, float)) else "no reporting window"
    )
    length_detail = (
        format(length, ".1f") + " tokens avg" if length else "not reported"
    )

    out["checks"] = [
        {"id": "reporting", "label": "Leg is reporting",
         "state": reporting, "detail": age_detail},
        {"id": "depth", "label": "Sample depth sufficient",
         "state": depth_ok, "detail": str(depth) + " batches in window"},
        {"id": "band", "label": "JSON fidelity in band",
         "state": in_band, "detail": band_detail},
        {"id": "length", "label": "Output length reported",
         "state": length_ok, "detail": length_detail},
        {"id": "cusum", "label": "CUSUM below threshold",
         "state": below_h, "detail": cusum_detail},
        {"id": "quorum", "label": "No quorum alert in 24h",
         "state": alert_free,
         "detail": current.get("last_alert_timestamp") or "none recorded"},
    ]

    yes = sum(1 for c in out["checks"] if c["state"] == "yes")
    no = sum(1 for c in out["checks"] if c["state"] == "no")
    out["yes_count"] = yes
    out["no_count"] = no
    out["unknown_count"] = 6 - yes - no
    return out


def main() -> int:
    DATA.mkdir(exist_ok=True)

    error = None
    try:
        legs = fetch(SOURCE)
    except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
        # A failed fetch must not overwrite good data with an empty
        # board. Keep the previous snapshot and mark it unreachable.
        legs = []
        error = str(exc)

    stamp = utcnow()

    if not legs:
        prev = {}
        if SNAPSHOT.exists():
            try:
                prev = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                prev = {}
        snapshot = prev or {"models": [], "generated_at": stamp}
        snapshot["reachable"] = False
        snapshot["error"] = error
        snapshot["checked_at"] = stamp
        SNAPSHOT.write_text(
            json.dumps(snapshot, indent=1) + "\n", encoding="utf-8"
        )
        print("[pulse] " + stamp + " UNREACHABLE: " + str(error))
        return 0

    # --- one history point per genuine gateway window ----------------
    # The gateway publishes a rolling average over its last 10 signal
    # batches, and its probes emit about twice a day. This job samples
    # four times a day, so roughly half of all runs observe a window
    # that has not moved.
    #
    # Recording those repeats would be actively harmful, not merely
    # redundant. CUSUM is a cumulative statistic: feeding it the same
    # observation twice accumulates S- at twice the true rate, so the
    # published "distance to alert" would advance twice as fast as
    # reality and the board would claim an alert was imminent when it
    # was not. Duplicates also deflate sigma0 by ~11%, tightening the
    # band against a baseline that only looks quiet because it is the
    # same number repeated.
    #
    # So a leg is recorded only when its window_end has advanced.
    prior = read_history()
    last_window = {}
    for row in prior:
        if row.get("window_end"):
            last_window[row.get("model_tuple")] = row["window_end"]

    appended, repeats = 0, 0
    with HISTORY.open("a", encoding="utf-8") as fh:
        for leg in legs:
            model = leg.get("model_tuple")
            window_end = leg.get("window_end")
            # No window means no observation to record. Without this, a
            # leg that never reports escapes the dedupe key (None never
            # matches) and appends a null-rate row every single run --
            # ~1460 a year, eventually evicting real observations under
            # MAX_HISTORY. It is still rendered on the board from the
            # live payload; it just contributes no history point.
            if not window_end:
                repeats += 1
                continue
            if last_window.get(model) == window_end:
                repeats += 1
                continue
            fh.write(json.dumps({
                "t": stamp,
                "model_tuple": model,
                "status": leg.get("status"),
                "json_success_rate": leg.get("recent_json_success_rate"),
                "avg_output_length": leg.get("recent_avg_output_length"),
                "window_age_hours": leg.get("window_age_hours"),
                "window_end": window_end,
            }, separators=(",", ":")) + "\n")
            appended += 1

    rows = read_history()
    if len(rows) > MAX_HISTORY:
        rows = rows[-MAX_HISTORY:]
        HISTORY.write_text(
            "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
            encoding="utf-8",
        )

    history = read_history()
    models = []
    for leg in legs:
        current = {
            "status": leg.get("status"),
            "window_age_hours": leg.get("window_age_hours"),
            "json_success_rate": leg.get("recent_json_success_rate"),
            "avg_output_length": leg.get("recent_avg_output_length"),
            "sample_count": leg.get("sample_count"),
            "last_alert_timestamp": leg.get("last_alert_timestamp"),
            "window_end": leg.get("window_end"),
        }
        models.append(analyse(leg.get("model_tuple"), history, current))

    snapshot = {
        "generated_at": stamp,
        "source": SOURCE,
        "reachable": True,
        "stale_after_hours": STALE_AFTER_HOURS,
        "observations": len(history),
        "models": models,
    }

    SNAPSHOT.write_text(
        json.dumps(snapshot, indent=1) + "\n", encoding="utf-8"
    )
    print("[pulse] " + stamp + " legs=" + str(len(models))
          + " recorded=" + str(appended) + " unchanged=" + str(repeats)
          + " observations=" + str(len(history)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
