#!/usr/bin/env python3
"""Command-line weight tracker. Data is stored in weights.csv next to the script.

If a day has several readings, they are averaged first; period averages
(weekly, monthly, overall) are then computed from those daily averages.

Examples:
  python weight.py add 72.5
  python weight.py add 72,1 --date 2026-11-10
  python weight.py show last --weeks 4
  python weight.py show avg
  python weight.py show trend --by week --last 8
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

CSV_FILE = Path(__file__).with_name("weights.csv")
STABLE = 0.3  # changes below this threshold (kg) count as "stable"


# ---------- helpers ----------

def parse_weight(s):
    try:
        w = float(s.replace(",", "."))
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid weight: {s}")
    if w <= 0:
        raise argparse.ArgumentTypeError("weight must be positive")
    return w


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("invalid date, use the format YYYY-MM-DD")


def mean(values):
    return sum(values) / len(values)


def pct(new, old):
    return (new - old) / old * 100


def arrow(delta):
    if abs(delta) < STABLE:
        return "→"
    return "↑" if delta > 0 else "↓"


def load_daily():
    """Read the CSV and return one (date, average, n_readings) tuple per day, sorted by date."""
    if not CSV_FILE.exists():
        return []
    by_day = defaultdict(list)
    with CSV_FILE.open(newline="") as f:
        for r in csv.DictReader(f):
            by_day[date.fromisoformat(r["date"])].append(float(r["weight"]))
    return [(d, mean(ws), len(ws)) for d, ws in sorted(by_day.items())]


def need_data():
    days = load_daily()
    if not days:
        sys.exit("No data yet. Add a weight with: weight.py add 72.5")
    return days


# ---------- commands ----------

def cmd_add(args):
    d = args.date or date.today()
    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "weight"])
        w.writerow([d.isoformat(), f"{args.weight:.1f}"])
    print(f"Saved: {d.isoformat()}  {args.weight:.1f} kg")


def cmd_last(args):
    days = need_data()
    n_days = args.days if args.days else (args.weeks or 4) * 7
    cutoff = date.today() - timedelta(days=n_days)
    days = [r for r in days if r[0] > cutoff]
    if not days:
        sys.exit("No data in the requested period.")

    prev = None
    for d, w, n in days:
        diff = "" if prev is None else f"{w - prev:+.2f}"
        note = f"  (avg of {n} readings)" if n > 1 else ""
        print(f"{d.isoformat()}  {w:6.2f} kg  {diff:>6}{note}")
        prev = w

    weights = [w for _, w, _ in days]
    print(f"\n{len(days)} days | avg {mean(weights):.2f} | "
          f"min {min(weights):.2f} | max {max(weights):.2f} | "
          f"change {weights[-1] - weights[0]:+.2f} kg")


def cmd_avg(args):
    days = need_data()
    weights = [w for _, w, _ in days]
    readings = sum(n for _, _, n in days)
    print(f"Overall average: {mean(weights):.2f} kg")
    print(f"Days: {len(days)} ({readings} readings), "
          f"{days[0][0].isoformat()} → {days[-1][0].isoformat()}")
    print(f"Min {min(weights):.2f} | Max {max(weights):.2f}")


def cmd_trend(args):
    days = need_data()
    by_week = args.by == "week"
    n = args.last or (8 if by_week else 6)

    groups = defaultdict(list)
    for d, w, _ in days:
        start = d - timedelta(days=d.weekday()) if by_week else d.replace(day=1)
        groups[start].append(w)

    periods = sorted(groups)[-n:]  # the last n periods that have data
    label = "Week of" if by_week else "Month of"
    print(f"{label:<12} {'Avg':>7} {'Days':>5} {'Δ kg':>7} {'Δ %':>8}")

    prev_avg = None
    first_avg = None
    for p in periods:
        avg = mean(groups[p])
        if prev_avg is None:
            delta_kg = delta_pct = "-"
            mark = ""
            first_avg = avg
        else:
            d = avg - prev_avg
            delta_kg = f"{d:+.2f}"
            delta_pct = f"{pct(avg, prev_avg):+.2f}%"
            mark = arrow(d)
        print(f"{p.isoformat():<12} {avg:7.2f} {len(groups[p]):5d} {delta_kg:>7} {delta_pct:>8}  {mark}")
        prev_avg = avg

    if len(periods) > 1:
        total = prev_avg - first_avg
        print(f"\nOverall trend: {first_avg:.2f} → {prev_avg:.2f} kg "
              f"({total:+.2f} kg, {pct(prev_avg, first_avg):+.2f}%) {arrow(total)}")


# ---------- main ----------

def main():
    if sys.argv[1:2] == ["help"]:
        sys.argv[1] = "-h"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    p = argparse.ArgumentParser(description="Weight tracker (data stored in weights.csv).")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{add,show,help}")

    a = sub.add_parser("add", help="add a weight (today, or use --date)")
    a.add_argument("weight", type=parse_weight, help="weight in kg, e.g. 72.5 or 72,5")
    a.add_argument("--date", type=parse_date, help="date as YYYY-MM-DD (default: today)")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("show", help="show data")
    ss = s.add_subparsers(dest="what", required=True)

    last = ss.add_parser("last", help="list the last weeks/days (default: 4 weeks)")
    g = last.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, help="last N days")
    g.add_argument("--weeks", type=int, help="last N weeks")
    last.set_defaults(func=cmd_last)

    ss.add_parser("avg", help="overall average").set_defaults(func=cmd_avg)

    t = ss.add_parser("trend", help="compare averages of consecutive periods")
    t.add_argument("--by", choices=["week", "month"], default="week", help="period (default: week)")
    t.add_argument("--last", type=int, help="how many periods to show (default: 8 weeks / 6 months)")
    t.set_defaults(func=cmd_trend)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
