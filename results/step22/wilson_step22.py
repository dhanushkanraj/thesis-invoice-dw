"""Step 22: Wilson 95% intervals for the Step 21 final results.
Counts are k = (percent / 100) * n, taken from the Step 21 score output (notes section 25).
Run: python wilson_step22.py   (needs matplotlib for the chart)"""
import math, csv
Z = 1.96
def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return p, c-h, c+h
# exact-match percent (digital, scanned) per set. held-out n=24, challenge n=40
EXACT = {
 "held-out":  {"n":24, "rows":[("M1 rules","-",100.0,12.5),
   ("M2 LLM alone","Qwen3 4B",75.0,16.7),("M2 LLM alone","Qwen2.5 3B",58.3,16.7),
   ("M3 LLM + validation","Qwen3 4B",79.2,16.7),("M3 LLM + validation","Qwen2.5 3B",58.3,16.7),
   ("M4 + perfect reviewer","Qwen3 4B",91.7,70.8),("M4 + perfect reviewer","Qwen2.5 3B",79.2,75.0)]},
 "challenge": {"n":40, "rows":[("M1 rules","-",0.0,0.0),
   ("M2 LLM alone","Qwen3 4B",92.5,10.0),("M2 LLM alone","Qwen2.5 3B",37.5,7.5),
   ("M3 LLM + validation","Qwen3 4B",92.5,10.0),("M3 LLM + validation","Qwen2.5 3B",37.5,7.5),
   ("M4 + perfect reviewer","Qwen3 4B",95.0,60.0),("M4 + perfect reviewer","Qwen2.5 3B",70.0,75.0)]},
}
# share of invoices flagged for review (digital, scanned)
FLAG = {
 "held-out":  {"n":24, "rows":[("Qwen3 4B",12.5,58.3),("Qwen2.5 3B",20.8,62.5)]},
 "challenge": {"n":40, "rows":[("Qwen3 4B",2.5,50.0),("Qwen2.5 3B",32.5,67.5)]},
}
def cell(pct, n):
    k = round(pct*n/100)
    assert abs(k/n*100 - pct) < 0.06, (pct, n, k)   # percent must be a whole count
    p, lo, hi = wilson(k, n)
    return k, p*100, max(lo,0.0)*100, hi*100
out = []
for ds, d in EXACT.items():
    for m, model, dig, sc in d["rows"]:
        for inp, pct in (("digital", dig), ("scanned", sc)):
            k, p, lo, hi = cell(pct, d["n"])
            out.append(["exact", ds, m, model, inp, k, d["n"], round(p,1), round(lo,1), round(hi,1)])
for ds, d in FLAG.items():
    for model, dig, sc in d["rows"]:
        for inp, pct in (("digital", dig), ("scanned", sc)):
            k, p, lo, hi = cell(pct, d["n"])
            out.append(["flagged", ds, "M3 flags", model, inp, k, d["n"], round(p,1), round(lo,1), round(hi,1)])
with open("wilson_results.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["measure","set","method","model","input","k","n","percent","wilson_low","wilson_high"]); w.writerows(out)
print(len(out), "rows written to wilson_results.csv")

# ---- chart (optional, needs matplotlib) ----
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    GREY, BLUE, ORANGE = "#8a8984", "#2a78d6", "#eb6834"   # rules / Qwen3 4B / Qwen2.5 3B
    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.family":"DejaVu Sans","text.color":INK,"axes.labelcolor":MUTED,
                         "xtick.color":MUTED,"ytick.color":MUTED})
    methods = ["M1 rules","M2 LLM alone","M3 LLM + validation","M4 + perfect reviewer"]
    short = ["M1\nrules","M2\nLLM alone","M3\n+ validation","M4\n+ perfect reviewer"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.6), dpi=200, sharey=True)
    for r, ds in enumerate(("held-out","challenge")):
        for c, inp in enumerate(("digital","scanned")):
            ax = axes[r][c]
            ax.set_axisbelow(True); ax.grid(axis="y", color=GRID, lw=0.8)
            for sp in ("top","right"): ax.spines[sp].set_visible(False)
            for sp in ("left","bottom"): ax.spines[sp].set_color(GRID)
            rows = [x for x in out if x[0]=="exact" and x[1]==ds and x[4]==inp]
            w = 0.34
            for i, m in enumerate(methods):
                for row in [x for x in rows if x[2].startswith(m.split()[0]) and x[2][:2]==m[:2]]:
                    model, pct, lo, hi = row[3], row[7], row[8], row[9]
                    if model == "-":      off, col = 0.0, GREY
                    elif model == "Qwen3 4B": off, col = -w/2, BLUE
                    else:                  off, col = +w/2, ORANGE
                    ax.bar(i+off, pct, width=w if model!="-" else w*1.4, color=col, zorder=3)
                    ax.errorbar(i+off, pct, yerr=[[pct-lo],[hi-pct]], fmt="none", ecolor=INK, elinewidth=1, capsize=3, zorder=4)
                    ax.text(i+off, min(hi+2.2, 104), f"{pct:.1f}", ha="center", va="bottom", fontsize=8, color=INK)
            ax.set_xticks(range(4)); ax.set_xticklabels(short, fontsize=8)
            ax.set_ylim(0, 112); ax.set_yticks(range(0,101,20))
            n = EXACT[ds]["n"]
            ax.set_title(f"{ds.capitalize()} set, {inp} invoices (n={n})", fontsize=10, loc="left", color=INK)
            if c==0: ax.set_ylabel("Whole invoice exactly correct (%)", fontsize=9)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=GREY,label="Rules (no model)"),Patch(color=BLUE,label="Qwen3 4B"),Patch(color=ORANGE,label="Qwen2.5 3B")],
               loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Whole-invoice exact match by method (bars) with Wilson 95% intervals (whiskers)", fontsize=11, x=0.01, ha="left")
    fig.text(0.01, 0.045, "M4 is an upper bound: a perfect reviewer simulated from the answer keys.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0,0.07,1,0.96))
    fig.savefig("fig_exact_match.png"); print("chart written: fig_exact_match.png")
except ImportError:
    print("matplotlib not installed: chart skipped")
