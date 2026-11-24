import argparse
from datetime import datetime, time as dt_time
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from zoneinfo import ZoneInfo

import requests

from storage import save_incidents, save_partition

ROOT_DIR = Path(__file__).resolve().parent.parent
PARIS_TZ = ZoneInfo("Europe/Paris")
API_URL = "https://prim.iledefrance-mobilites.fr/marketplace/requete-ligne"
INCIDENTS_API_URL = "https://prim.iledefrance-mobilites.fr/marketplace/general-message"

LINES = {
    "rer_b": {"ref": "STIF:Line::C01743:", "key_idx": 0, "storage": "rer-b"},
    "rer_d": {"ref": "STIF:Line::C01728:", "key_idx": 1, "storage": "rer-d"},
    "rer_a": {"ref": "STIF:Line::C01742:", "key_idx": 1, "storage": "rer-a"},
}

DIRECTION_KEYWORDS = {
    "rer_b": {
        "Nord": ("mitry", "aéroport", "aeroport", "cdg", "aulnay"),
        "Sud": ("saint-rémy", "saint-remy", "robinson", "massy", "orsay", "laplace", "denfert"),
    },
    "rer_d": {
        "Nord": ("creil", "orry", "goussainville", "villiers", "stade de france"),
        "Sud": ("melun", "corbeil", "malesherbes", "juvisy", "evry"),
    },
    "rer_a": {
        "Ouest": ("cergy", "poissy", "saint-germain", "nanterre", "rueil"),
        "Est": ("marne", "boissy", "torcy", "chessy", "joinville"),
    },
}


def load_api_keys():
    """Lit les clés PRIM depuis les variables d'environnement."""
    k1 = os.getenv("PRIM_API_KEY", "").strip()
    k2 = os.getenv("PRIM_API_KEY_2", "").strip() or k1
    return [k1, k2]


def load_stations():
    stations_file = ROOT_DIR / "data" / "stations.json"
    if not stations_file.exists():
        return {}
    try:
        return json.loads(stations_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_night_time(now):
    return dt_time(1, 30) <= now.time() < dt_time(4, 45)


def first_value(items, default=""):
    if items and isinstance(items, list):
        return items[0].get("value", default)
    return default


def infer_direction(line_id, destination, fallback=""):
    dest = (destination or "").lower()
    for direction, keywords in DIRECTION_KEYWORDS.get(line_id, {}).items():
        if any(kw in dest for kw in keywords):
            return direction
    return fallback


def fetch_prim(url, api_key, line_ref, timeout=30):
    resp = requests.get(
        url,
        params={"LineRef": line_ref},
        headers={"apikey": api_key, "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def parse_incident(im, line_id, now_str):
    msg_id = im.get("InfoMessageIdentifier", {}).get("value") or im.get("ItemIdentifier", "")
    channel = im.get("InfoChannelRef", {}).get("value", "")
    rec_at = im.get("RecordedAtTime", "")
    valid_until = im.get("ValidUntilTime", "")

    short_msg, text_msg = "", ""
    for msg in im.get("Content", {}).get("Message", []):
        m_type = msg.get("MessageType", "")
        txt = (msg.get("MessageText") or {}).get("value", "")
        if m_type == "SHORT_MESSAGE":
            short_msg = txt
        elif m_type == "TEXT_ONLY":
            text_msg = txt
        elif not text_msg:
            text_msg = txt

    short_msg = short_msg or text_msg
    text_msg = text_msg or short_msg
    if not msg_id:
        digest = hashlib.md5(short_msg.encode("utf-8")).hexdigest()[:8]
        msg_id = f"{line_id}_{rec_at}_{digest}"

    return {
        "message_id": msg_id,
        "line": line_id,
        "channel": channel,
        "recorded_at": rec_at,
        "valid_until": valid_until,
        "short_message": short_msg,
        "message": text_msg,
        "first_seen": now_str,
        "last_seen": now_str,
    }


def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def parse_call(call, stations):
    ref = call.get("StopPointRef", {}).get("value", "")
    name = stations.get(ref, first_value(call.get("DestinationDisplay"), ref))

    aimed_arr = parse_dt(call.get("AimedArrivalTime"))
    exp_arr = parse_dt(call.get("ExpectedArrivalTime"))
    aimed_dep = parse_dt(call.get("AimedDepartureTime"))
    exp_dep = parse_dt(call.get("ExpectedDepartureTime"))

    delay = 0
    if exp_dep and aimed_dep:
        delay = int((exp_dep - aimed_dep).total_seconds())
    elif exp_arr and aimed_arr:
        delay = int((exp_arr - aimed_arr).total_seconds())

    platform = (call.get("DeparturePlatformName") or call.get("ArrivalPlatformName") or {}).get("value", "")
    return {
        "stop_ref": ref,
        "stop_name": name,
        "aimed_arrival": aimed_arr.isoformat() if aimed_arr else "",
        "aimed_departure": aimed_dep.isoformat() if aimed_dep else "",
        "expected_arrival": exp_arr.isoformat() if exp_arr else "",
        "expected_departure": exp_dep.isoformat() if exp_dep else "",
        "delay_sec": delay,
        "platform": platform,
        "status": call.get("DepartureStatus") or call.get("ArrivalStatus") or "",
    }


def train_to_row(train, disappeared=False):
    sorted_stops = sorted(train["stops"].items(), key=lambda item: train["stop_orders"].get(item[0], 999))
    prev_delay = 0
    max_added = 0
    worst_stop = ""
    compact_stops = []

    for ref, stop in sorted_stops:
        delay = stop.get("delay_sec", 0)
        added = delay - prev_delay
        if added > max_added:
            max_added = added
            worst_stop = stop.get("stop_name", "")
        # o=ordre, n=nom, ad/ed=horaires, dt/da=retard/delta, v=voie, s=statut
        compact_stops.append({
            "o": train["stop_orders"].get(ref, 0),
            "n": stop.get("stop_name", ""),
            "ad": stop.get("aimed_departure") or stop.get("aimed_arrival", ""),
            "ed": stop.get("expected_departure") or stop.get("expected_arrival", ""),
            "dt": delay,
            "da": added,
            "v": stop.get("platform", ""),
            "s": stop.get("status", ""),
        })
        prev_delay = delay

    meta = train["meta"]
    return {
        "journey_id": train["journey_id"],
        "line": train["line"],
        "mission": meta.get("mission", ""),
        "origin": meta.get("origin", ""),
        "destination": meta.get("destination", ""),
        "direction": meta.get("direction", ""),
        "is_long": meta.get("is_long", False),
        "nb_stops": len(train["stops"]),
        "total_delay_sec": compact_stops[-1]["dt"] if compact_stops else 0,
        "max_delay_added_sec": max_added,
        "worst_stop": worst_stop,
        "disappeared": disappeared,
        "first_seen": train["first_seen"],
        "last_seen": train["last_seen"],
        "stops": json.dumps(compact_stops, ensure_ascii=False),
    }


def poll_incidents(line_id, cfg, api_key, active_incidents, now_str):
    """Récupère les messages d'incidents actifs sur une ligne."""
    data = fetch_prim(INCIDENTS_API_URL, api_key, cfg["ref"])
    deliveries = data.get("Siri", {}).get("ServiceDelivery", {}).get("GeneralMessageDelivery", [])

    seen_ids = set()
    rows = []
    for deliv in deliveries:
        for im in deliv.get("InfoMessage", []):
            row = parse_incident(im, line_id, now_str)
            mid = row["message_id"]
            seen_ids.add(mid)
            key = (line_id, mid)
            if key in active_incidents:
                row["first_seen"] = active_incidents[key]["first_seen"]
            active_incidents[key] = row
            rows.append(dict(row))

    for key in [k for k in active_incidents if k[0] == line_id and k[1] not in seen_ids]:
        active_incidents.pop(key, None)

    return rows


def poll_trains(line_id, cfg, api_key, stations, active_trains, now_str):
    """Met à jour les trains actifs d'une ligne et renvoie ceux sortis du flux."""
    data = fetch_prim(API_URL, api_key, cfg["ref"])
    deliveries = data.get("Siri", {}).get("ServiceDelivery", {}).get("EstimatedTimetableDelivery", [])

    seen_ids = set()
    for deliv in deliveries:
        for frame in deliv.get("EstimatedJourneyVersionFrame", []):
            for vj in frame.get("EstimatedVehicleJourney", []):
                ref = vj.get("DatedVehicleJourneyRef", {})
                jid = ref.get("value", "") if isinstance(ref, dict) else str(ref or "")
                if not jid:
                    continue
                seen_ids.add(jid)

                if jid not in active_trains:
                    dest = first_value(vj.get("DestinationName")) or first_value(vj.get("DestinationDisplay"))
                    fallback_dir = (vj.get("DirectionRef") or {}).get("value", "")
                    active_trains[jid] = {
                        "journey_id": jid,
                        "line": line_id,
                        "meta": {
                            "mission": first_value(vj.get("PublishedLineName")),
                            "origin": first_value(vj.get("OriginName")),
                            "destination": dest,
                            "direction": infer_direction(line_id, dest, fallback=fallback_dir),
                            "is_long": "longTrain" in vj.get("VehicleFeatureRef", []),
                        },
                        "first_seen": now_str,
                        "last_seen": now_str,
                        "stops": {},
                        "stop_orders": {},
                    }

                train = active_trains[jid]
                train["last_seen"] = now_str
                calls = vj.get("EstimatedCalls", {}).get("EstimatedCall", [])
                for order, call in enumerate(calls, start=1):
                    call_info = parse_call(call, stations)
                    stop_ref = call_info["stop_ref"]
                    train["stop_orders"].setdefault(stop_ref, order)
                    train["stops"][stop_ref] = call_info

    # Un train qui disparaît vite alors qu'il lui restait >5 arrêts est probablement supprimé
    finished_rows = []
    for jid in set(active_trains.keys()) - seen_ids:
        train = active_trains.pop(jid)
        duration = (datetime.fromisoformat(train["last_seen"]) - datetime.fromisoformat(train["first_seen"])).total_seconds()
        disappeared = duration < 300 and len(train["stops"]) > 5
        finished_rows.append(train_to_row(train, disappeared=disappeared))

    return finished_rows


def run_collector(keys, selected_lines=None, interval=120, incident_interval=300, once=False):
    """Boucle principale de collecte des trains et incidents."""
    stations = load_stations()
    target_lines = {k: v for k, v in LINES.items() if not selected_lines or k in selected_lines}
    active = {k: {} for k in target_lines}
    buffers = {k: [] for k in target_lines}
    active_incidents = {}

    last_incident_poll = 0.0
    current_day = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    poll_count = 0

    def stop_collector(*_):
        raise SystemExit

    signal.signal(signal.SIGTERM, stop_collector)

    def flush(line_id=None):
        targets = [line_id] if line_id else list(target_lines.keys())
        for lid in targets:
            if buffers[lid]:
                save_partition(buffers[lid], current_day, prefix=target_lines[lid]["storage"])
                buffers[lid].clear()

    def flush_final():
        for lid in target_lines:
            for train in active[lid].values():
                buffers[lid].append(train_to_row(train, disappeared=False))
            active[lid].clear()
            flush(lid)

    try:
        while True:
            now = datetime.now(PARIS_TZ)
            if is_night_time(now):
                if any(active.values()) or any(buffers.values()):
                    flush_final()
                time.sleep(300)
                continue

            poll_count += 1
            now_str = now.isoformat()
            today = now.strftime("%Y-%m-%d")
            if today != current_day:
                flush()
                current_day = today

            if time.time() - last_incident_poll >= incident_interval:
                last_incident_poll = time.time()
                incident_rows = []
                for line_id, cfg in target_lines.items():
                    try:
                        incident_rows.extend(poll_incidents(line_id, cfg, keys[cfg["key_idx"]], active_incidents, now_str))
                    except Exception as e:
                        print(line_id, e)
                if incident_rows:
                    save_incidents(incident_rows, current_day)

            for line_id, cfg in target_lines.items():
                try:
                    finished = poll_trains(line_id, cfg, keys[cfg["key_idx"]], stations, active[line_id], now_str)
                    buffers[line_id].extend(finished)
                    if len(buffers[line_id]) >= 20 or (poll_count % 10 == 0 and buffers[line_id]):
                        flush(line_id)
                except Exception as e:
                    print(line_id, e)

            if once:
                break
            time.sleep(interval)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        flush_final()


def main():
    parser = argparse.ArgumentParser(description="Collecteur temps réel PRIM pour les RER A, B et D")
    parser.add_argument("--line", choices=list(LINES.keys()), help="Ligne à collecter (par défaut : toutes)")
    parser.add_argument("--interval", type=int, default=120, help="Intervalle entre deux collectes en secondes")
    parser.add_argument("--once", action="store_true", help="Exécuter un seul cycle puis quitter")
    args = parser.parse_args()

    keys = load_api_keys()
    if not keys[0]:
        raise ValueError("PRIM_API_KEY manquante")

    selected = [args.line] if args.line else None
    run_collector(keys, selected_lines=selected, interval=args.interval, once=args.once)


main()
