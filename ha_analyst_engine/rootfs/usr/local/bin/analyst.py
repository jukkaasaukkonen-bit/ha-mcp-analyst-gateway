#!/usr/bin/env python3
"""Read-only device analytics; optional write is limited to a persistent notification."""
import datetime as dt
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from learning import analyze

DATA = Path("/data/analyst")
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "learning.sqlite3"
BASE = "http://supervisor/core"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CONFIG = json.loads(Path("/data/options.json").read_text()) if Path("/data/options.json").exists() else {}
ZONE = ZoneInfo(CONFIG.get("timezone", "Europe/Helsinki"))
HOUR = int(CONFIG.get("report_hour", 8))
MINUTE = int(CONFIG.get("report_minute", 0))
INTERVAL = max(5, min(60, int(CONFIG.get("sample_interval_minutes", 15))))
NOTIFY = bool(CONFIG.get("notify_persistent", True))

# Explicit allowlist. Expand only after verifying entity IDs on the user's HA.
ENTITIES = [
 "switch.technical_room_ivt490_shelly",
 "sensor.heating_optimizer_v1_5_production_readiness",
 "sensor.heating_optimizer_v1_5_final_shadow_mode",
 "sensor.heating_optimizer_v1_5_final_ext_recommendation",
 "sensor.heating_optimizer_v1_5_cooling_risk",
 "binary_sensor.heating_optimizer_v1_5_sustained_cooling_risk",
 "sensor.ivt490_lammontarve_v3",
 "sensor.h66_5fab_watchdog_v1",
 "sensor.koti_room_temperature",
 "sensor.bedroom_timmerflotte_temp_hmd_sensor_temperature",
 "counter.heating_optimizer_v1_completed_cycles",
 "counter.heating_optimizer_v1_normal_cycles",
 "counter.heating_optimizer_v1_safety_interrupted_cycles",
 "counter.heating_optimizer_v1_short_invalid_cycles",
 "timer.ivt490_palautumisaika",
 "timer.ivt490_ext_maksimiaika",
 "input_text.ivt490_ext_viimeisin_katkaisusyy",
 "input_text.heating_optimizer_v1_last_result",
 "sensor.kokonaissaasto_tanaan",
 "sensor.ivt490_accumulated_consumption",
 "sensor.ivt490_nettosaasto_tanaan",
 "sensor.ivt490_nettosaasto_tassa_kuussa",
]

def read_states():
    if not TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN unavailable; refusing unauthenticated reads")
    req = urllib.request.Request(
        BASE + "/api/states",
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/json"},
        method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError("Home Assistant returned HTTP " + str(resp.status))
        payload = json.load(resp)
    return {v["entity_id"]: v for v in payload if v.get("entity_id") in ENTITIES}

def db_open():
    db = sqlite3.connect(DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS samples (
        ts TEXT NOT NULL, entity TEXT NOT NULL, state TEXT NOT NULL,
        PRIMARY KEY(ts,entity))""")
    db.execute("""CREATE TABLE IF NOT EXISTS reports (
        day TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (day TEXT PRIMARY KEY, sent_at TEXT NOT NULL)""")
    db.commit()
    return db

def record(db, values, now):
    db.executemany("INSERT OR REPLACE INTO samples VALUES(?,?,?)",
        [(now.isoformat(), e, str(v.get("state", "unknown"))) for e,v in values.items()])
    db.commit()

def numeric(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def notify_once(db, day, payload):
    """Only permitted HA write: persistent_notification.create. Never device control."""
    if not NOTIFY or db.execute("SELECT 1 FROM notifications WHERE day=?", (day,)).fetchone():
        return
    if not TOKEN:
        raise RuntimeError("Missing Supervisor API token")
    issues = payload["findings"][:5]
    summary = "\n".join("- %s: %s" % (x["priority"], x["finding"]) for x in issues)
    message = ("Tila: %s | Havainnot: %d\n\n%s\n\n" %
        (payload["status"], len(payload["findings"]), summary or "Ei sääntöjen tunnistamia poikkeamia."))
    message += "Mittauskattavuus 24 h: %s. %s" % (
        payload["data_quality"]["coverage_24h_pct"],
        "Raportti on alustava." if payload["data_quality"]["provisional"] else "")
    body = json.dumps({"title":"HA Analyst | " + day,
        "message":message, "notification_id":"ha_analyst_daily"}).encode()
    req = urllib.request.Request(BASE + "/api/services/persistent_notification/create",
        data=body, method="POST", headers={"Authorization":"Bearer " + TOKEN,
        "Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status not in (200,201):
            raise RuntimeError("Notification returned HTTP %d" % response.status)
    db.execute("INSERT INTO notifications VALUES (?,?)",(day,dt.datetime.now(ZONE).isoformat()))
    db.commit()
    print("[NOTIFY] Persistent notification created",flush=True)

def report(db, values, now):
    state = lambda e: values.get(e, {}).get("state", "missing")
    rows = db.execute("SELECT entity,state,ts FROM samples WHERE ts >= ?",
        ((now-dt.timedelta(days=7)).isoformat(),)).fetchall()
    by_entity={}
    for e,v,t in rows: by_entity.setdefault(e,[]).append((v,t))
    rows24 = [r for r in rows if r[2] >= (now-dt.timedelta(hours=24)).isoformat()]
    unique_times = len(set(r[2] for r in rows24))
    expected = max(1, int(24*60/INTERVAL))
    coverage = round(min(100,100*unique_times/expected),1)
    issues=[]
    missing=[e for e in ENTITIES if state(e) == "missing"]
    unhealthy=[e for e in ENTITIES if state(e) in ("unknown","unavailable")]
    if missing: issues.append({"priority":"P2","finding":"Configured entities missing","entities":missing})
    if unhealthy: issues.append({"priority":"P2","finding":"Unknown/unavailable entities","entities":unhealthy})
    if state("sensor.h66_5fab_watchdog_v1") not in ("OK","missing"):
        issues.append({"priority":"P1","finding":"H66 watchdog not OK","state":state("sensor.h66_5fab_watchdog_v1")})
    if state("switch.technical_room_ivt490_shelly")=="on" and state("timer.ivt490_palautumisaika")=="active":
        issues.append({"priority":"P1","finding":"EXT active during recovery timer"})
    if state("binary_sensor.heating_optimizer_v1_5_sustained_cooling_risk")=="on" and state("switch.technical_room_ivt490_shelly")=="on":
        issues.append({"priority":"P1","finding":"EXT active with sustained cooling risk; verify controller timing"})
    metrics={}
    for e in ("sensor.koti_room_temperature","sensor.bedroom_timmerflotte_temp_hmd_sensor_temperature"):
        nums=[numeric(v) for v,_ in by_entity.get(e,[])]
        nums=[x for x in nums if x is not None]
        if nums: metrics[e]={"min":round(min(nums),2),"max":round(max(nums),2),"avg":round(sum(nums)/len(nums),2),"samples":len(nums)}
    cycles={}
    for e in ("counter.heating_optimizer_v1_completed_cycles","counter.heating_optimizer_v1_normal_cycles","counter.heating_optimizer_v1_safety_interrupted_cycles","counter.heating_optimizer_v1_short_invalid_cycles"):
        nums=[numeric(v) for v,_ in by_entity.get(e,[])]
        nums=[x for x in nums if x is not None]
        if len(nums)>=2:
            # Counter resets/restarts invalidate naive delta; never claim verified totals.
            cycles[e]={"observed_start":nums[0],"observed_end":nums[-1],"delta_if_monotonic":round(nums[-1]-nums[0],2) if all(b>=a for a,b in zip(nums,nums[1:])) else None}
    learning = analyze(rows, now, INTERVAL)
    issues.extend(learning['findings'])
    # Record learning hypotheses with stable identifiers for future comparison.
    db.execute("""CREATE TABLE IF NOT EXISTS hypotheses (
        id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
        status TEXT NOT NULL, confidence TEXT NOT NULL, evidence TEXT NOT NULL)""")
    for hypothesis in learning['hypotheses']:
        db.execute("""INSERT INTO hypotheses (id,first_seen,last_seen,status,confidence,evidence)
            VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            last_seen=excluded.last_seen,status=excluded.status,
            confidence=excluded.confidence,evidence=excluded.evidence""",
            (hypothesis['id'],now.isoformat(),now.isoformat(),hypothesis['status'],
             hypothesis['confidence'],json.dumps(hypothesis,ensure_ascii=False)))
    db.commit()
    # No GREEN when sampling has not yet accumulated adequate evidence.
    if coverage < 75 or not learning['windows']['1d']['mature']:
        issues.append({"priority":"P2","finding":"Insufficient 24h sampling coverage","coverage_pct":coverage})
    status="RED" if any(i["priority"]=="P1" for i in issues) else "AMBER" if issues else "GREEN"
    payload={"date":now.date().isoformat(),"generated_at":now.isoformat(),"status":status,
             "source":"HA API /api/states only; sampled snapshots; not full Recorder or logs",
             "data_quality":{"available":len(values),"configured":len(ENTITIES),"seven_day_samples":len(rows),"samples_24h":unique_times,"expected_samples_24h":expected,"coverage_24h_pct":coverage,"provisional":coverage<75 or not learning['windows']['1d']['mature']},
             "current":{e:state(e) for e in ENTITIES},
             "temperature_7d":metrics,"cycle_counters_7d":cycles,"optimization":learning,
             "findings":issues,
             "learning_note":"7/30/90 day baselines and evidence-ranked hypotheses; no automatic control changes.",
             "limitations":["No HA system log, trace, recorder history or verified electricity cost attribution in v1.2",
                            "ChatGPT scheduled tasks are not connected to this local report automatically."]}
    db.execute("INSERT OR REPLACE INTO reports VALUES(?,?,?)",
               (now.date().isoformat(),now.isoformat(),json.dumps(payload,ensure_ascii=False)))
    db.commit()
    (DATA/"latest.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    # Atomic export to a shared folder. No HA token or database is exported.
    try:
        import os as _os
        shared = Path("/share/ha_analyst_reports")
        shared.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(payload, indent=2, ensure_ascii=False)
        tmp = shared / ("." + now.date().isoformat() + ".tmp")
        tmp.write_text(blob, encoding="utf-8")
        _os.chmod(tmp, 0o644)
        _os.replace(tmp, shared / (now.date().isoformat() + ".json"))
        latest_tmp = shared / ".latest.tmp"
        latest_tmp.write_text(blob, encoding="utf-8")
        _os.chmod(latest_tmp, 0o644)
        _os.replace(latest_tmp, shared / "latest.json")
        print("[EXPORT] Report available in /share/ha_analyst_reports", flush=True)
    except Exception as export_exc:
        print("[EXPORT_ERROR] " + str(export_exc)[:180], flush=True)
    (DATA/"latest.txt").write_text(
       f"HA ANALYST {payload['date']} | {status} | {len(issues)} findings\n"+
       "\n".join(f"{i['priority']}: {i['finding']}" for i in issues)+
       "\nData: "+str(len(values))+"/"+str(len(ENTITIES))+" configured entities\n")
    print("[REPORT] "+json.dumps({"date":payload["date"],"status":status,"findings":issues,"coverage_24h_pct":coverage},ensure_ascii=False),flush=True)
    try:
        notify_once(db,now.date().isoformat(),payload)
    except Exception as exc:
        print("[NOTIFY_ERROR] %s: %s" % (type(exc).__name__,str(exc)[:180]),flush=True)

def export_existing_latest():
    source = DATA / "latest.json"
    if not source.is_file():
        return
    try:
        import os as _os
        import re as _re
        payload = json.loads(source.read_text(encoding="utf-8"))
        shared = Path("/share/ha_analyst_reports")
        shared.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(payload, indent=2, ensure_ascii=False)
        tmp = shared / ".latest.tmp"
        tmp.write_text(blob, encoding="utf-8")
        _os.chmod(tmp, 0o644)
        _os.replace(tmp, shared / "latest.json")
        date = payload.get("date", "")
        if isinstance(date, str) and _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            dated = shared / (date + ".json")
            if not dated.exists():
                dated.write_text(blob, encoding="utf-8")
                _os.chmod(dated, 0o644)
        print("[EXPORT] Existing latest report copied to shared feed", flush=True)
    except Exception as exc:
        print("[EXPORT_ERROR] Existing report: " + str(exc)[:180], flush=True)

def main():
    export_existing_latest()
    db=db_open()
    last_sample=0
    print("[START] Read-only analyst, report at %02d:%02d %s" % (HOUR,MINUTE,ZONE),flush=True)
    while True:
        now=dt.datetime.now(ZONE)
        if time.monotonic()-last_sample>=INTERVAL*60 or last_sample==0:
            try:
                values=read_states()
                record(db,values,now)
                print("[SAMPLE] %s entities=%d" % (now.isoformat(),len(values)),flush=True)
                last_sample=time.monotonic()
            except Exception as exc:
                print("[ERROR] Data acquisition: %s: %s" % (type(exc).__name__,str(exc)[:200]),flush=True)
                last_sample=time.monotonic()
        if now.hour==HOUR and now.minute>=MINUTE and now.minute<MINUTE+2:
            if not db.execute("SELECT 1 FROM reports WHERE day=?",(now.date().isoformat(),)).fetchone():
                try:
                    values=read_states()
                    record(db,values,now)
                    report(db,values,now)
                except Exception as exc:
                    print("[ERROR] Report: %s: %s" % (type(exc).__name__,str(exc)[:200]),flush=True)
        time.sleep(20)

if __name__=="__main__": main()
