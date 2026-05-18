"""Extract embedded mock data from roaduserintelligence.com RTI SPA bundle."""
import json
import re
import urllib.request
from pathlib import Path

URL = "https://roaduserintelligence.com/assets/index-C8SuGvqV.js"

def parse_num(s: str) -> int:
    return int(float(s))


def main():
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RTI-Dashboard/1.0)"},
    )
    js = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")

    out = {}

    # Risk hotspots
    m = re.search(
        r"\[(\{location:\"[^\"]+\",riskScore:\d+,incidents:\d+,primaryIssue:\"[^\"]+\"\}"
        r"(?:,\{location:\"[^\"]+\",riskScore:\d+,incidents:\d+,primaryIssue:\"[^\"]+\"\})*)\]",
        js,
    )
    if m:
        raw = "[" + m.group(1) + "]"
        # crude JS -> JSON
        raw = re.sub(r"(\w+):", r'"\1":', raw)
        try:
            out["hotspots"] = json.loads(raw)
        except json.JSONDecodeError:
            out["hotspots_raw"] = m.group(0)[:2000]

    # Monthly trend
    trend = re.findall(
        r'\{date:"([A-Za-z]{3} \d{2})",motorcycles:(\d+(?:e\d+)?),helmeted:(\d+(?:e\d+)?),violations:(\d+(?:e\d+)?)\}',
        js,
    )
    if trend:
        out["monthly_trend"] = [
            {
                "date": d,
                "motorcycles": parse_num(mc),
                "helmeted": parse_num(h),
                "violations": parse_num(v),
            }
            for d, mc, h, v in trend
        ]

    # Helmet compliance summary object
    for pat in [
        r'\{rate:(\d+(?:\.\d+)?),withHelmet:(\d+),withoutHelmet:(\d+)\}',
        r'withHelmet:(\d+),withoutHelmet:(\d+),rate:(\d+(?:\.\d+)?)',
    ]:
        m2 = re.search(pat, js)
        if m2:
            g = m2.groups()
            if len(g) == 3:
                if pat.startswith(r"\{rate"):
                    out["helmet_compliance"] = {
                        "rate": float(g[0]),
                        "withHelmet": int(g[1]),
                        "withoutHelmet": int(g[2]),
                    }
                else:
                    out["helmet_compliance"] = {
                        "withHelmet": int(g[0]),
                        "withoutHelmet": int(g[1]),
                        "rate": float(g[2]),
                    }
            break

    # Vehicle mix / daily stats patterns
    for key, pat in [
        ("vehicle_mix", r'Motorcycles:"[^"]+",Cars:"[^"]+"'),
        ("stat_values", r'value:(\d+(?:\.\d+)?(?:e\d+)?),label:"([^"]+)"'),
    ]:
        found = re.findall(pat, js) if "value:" in pat else re.findall(pat, js)
        if found and key == "stat_values":
            out[key] = [{"value": v, "label": l} for v, l in found[:20]]

    # Site compliance trend (multi-series)
    sites = re.findall(
        r'\{site:"([^"]+)",compliance:(\d+(?:\.\d+)?)\}',
        js,
    )
    if sites:
        out["site_compliance"] = [
            {"site": s, "compliance": float(c)} for s, c in sites
        ]

    # Injury / outcome data
    injury = re.findall(
        r'\{category:"([^"]+)",count:(\d+),severity:"([^"]+)"\}',
        js,
    )
    if injury:
        out["injuries"] = [
            {"category": c, "count": int(n), "severity": s} for c, n, s in injury
        ]

    # Time-of-day pattern
    tod = re.findall(
        r'\{hour:"([^"]+)",motorcycles:(\d+),violations:(\d+)\}',
        js,
    )
    if tod:
        out["time_of_day"] = [
            {"hour": h, "motorcycles": int(m), "violations": int(v)} for h, m, v in tod
        ]

    # Observation sites
    sites_obs = re.findall(r'value:"(OBS-\d+)",label:"([^"]+)"', js)
    if sites_obs:
        out["observation_sites"] = [{"id": v, "label": l} for v, l in sites_obs]

    # Multi-modal volume trend (cars, trucks, pedestrians per month)
    multimodal = re.findall(
        r'\{date:"([A-Za-z]{3} \d{2})",motorcycles:(\d+(?:\.\d+)?(?:e\d+)?),cars:(\d+(?:\.\d+)?(?:e\d+)?),trucks:(\d+(?:\.\d+)?(?:e\d+)?),pedestrians:(\d+(?:\.\d+)?(?:e\d+)?)\}',
        js,
    )
    if multimodal:
        out["multimodal_trend"] = [
            {
                "date": d,
                "motorcycles": parse_num(mc),
                "cars": parse_num(c),
                "trucks": parse_num(t),
                "pedestrians": parse_num(p),
            }
            for d, mc, c, t, p in multimodal
        ]

    # Site-level compliance bars
    site_comp = re.findall(
        r'\{site:"([^"]+)",compliance:(\d+(?:\.\d+)?),target:(\d+(?:\.\d+)?)\}',
        js,
    )
    if site_comp:
        out["site_compliance"] = [
            {"site": s, "compliance": float(c), "target": float(t)}
            for s, c, t in site_comp
        ]

    # Vehicle mix totals
    mix = re.search(
        r'\[(\{type:"motorcycle",count:\d+,trend:[-\d.]+\}(?:,\{type:"[^"]+",count:\d+,trend:[-\d.]+\})*)\]',
        js,
    )
    if mix:
        raw = "[" + mix.group(1) + "]"
        raw = re.sub(r"(\w+):", r'"\1":', raw)
        try:
            out["vehicle_mix"] = json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Per-site operational records
    sites_detail = re.findall(
        r'\{id:"(OBS-\d+)",location:"([^"]+)",totalDetections:(\d+(?:e\d+)?),motorcycles:(\d+(?:e\d+)?),helmetRate:(\d+(?:\.\d+)?),status:"([^"]+)",lastUpdate:"([^"]+)"\}',
        js,
    )
    if sites_detail:
        out["sites_detail"] = [
            {
                "id": sid,
                "location": loc,
                "totalDetections": parse_num(td),
                "motorcycles": parse_num(mc),
                "helmetRate": float(hr),
                "status": st,
                "lastUpdate": lu,
            }
            for sid, loc, td, mc, hr, st, lu in sites_detail
        ]

    # Violation types breakdown
    vtypes = re.findall(
        r'\{type:"([^"]+)",count:(\d+(?:\.\d+)?(?:e\d+)?),pct:(\d+(?:\.\d+)?)\}',
        js,
    )
    if vtypes:
        out["violation_types"] = [
            {"type": t, "count": parse_num(c), "pct": float(p)} for t, c, p in vtypes
        ]

    # Debug: all distinct date-object shapes
    date_objs = re.findall(r'\{date:"[A-Za-z]{3} \d{2}"[^}]+\}', js)
    shapes = sorted(set(re.sub(r"\d+(?:\.\d+)?(?:e\d+)?", "N", o) for o in date_objs))
    if shapes:
        out["_date_shapes"] = shapes[:15]

    # Per-site compliance (alternate key names)
    for pat in [
        r'\{name:"([^"]+)",compliance:(\d+(?:\.\d+)?),violations:(\d+)\}',
        r'\{location:"([^"]+)",compliance:(\d+(?:\.\d+)?)\}',
        r'complianceRate:(\d+(?:\.\d+)?),siteName:"([^"]+)"',
    ]:
        found = re.findall(pat, js)
        if found and "site_compliance_detail" not in out:
            out["site_compliance_detail"] = found[:15]

    # Save static JSON for dashboard consumption
    out_path = Path(__file__).resolve().parent / "rti_public_data.json"
    clean = {k: v for k, v in out.items() if not k.startswith("_")}
    out_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    print(json.dumps(clean, indent=2))


if __name__ == "__main__":
    main()
