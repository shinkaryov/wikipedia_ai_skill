"""One-page brief generated directly from computed metrics, with no LLM arithmetic."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from core import ResearchError

LABELS = {
    "missing_article": "no equivalent article", "ambiguous_article": "ambiguous article",
    "mapping_mismatch": "concept mapping mismatch", "incomplete_article_data": "missing article months",
    "incomplete_project_data": "missing project totals", "article_created_during_period": "article created within period",
    "manual_mapping_review_required": "manual topic proxy", "inconsistent_article_project_counts": "inconsistent counts",
    "less_than_24_months": "less than 24 months", "zero_baseline": "zero baseline", "low_baseline": "small baseline",
    "raw_normalized_direction_differs": "raw and relative trends differ", "direction_sensitive_to_one_pair": "direction changes when one month pair is omitted",
    "possible_spikes": "possible spikes", "concentrated_in_peak_month": "peak month exceeds 25% of annual views",
    "api_error": "API request failed",
}


def pct(value):
    return "n/a" if value is None else f"{value:+.1f}%"


def number(value):
    return "n/a" if value is None else f"{value:,.0f}"


def observations(result):
    notes = []
    for m in result["metrics"]:
        lang = m["language"].upper()
        if m["yoy_pct"] is None:
            notes.append(f"{lang}: growth unavailable ({'; '.join(LABELS.get(f, f) for f in m['flags'][:2]) or 'insufficient data'}).")
            continue
        sensitivity = m["leave_one_pair_out_yoy_range"]
        text = f"{lang}: {pct(m['yoy_pct'])} raw; {pct(m['normalized_yoy_pct'])} relative to project traffic."
        if sensitivity:
            text += f" Omitting each matched month pair gives {pct(sensitivity[0])} to {pct(sensitivity[1])}."
        if m["flags"]:
            text += " Check: " + "; ".join(LABELS.get(f, f) for f in m["flags"][:2]) + "."
        notes.append(text)
    return notes


def next_step(result):
    ranked = result["priority"]["research_next"]
    if ranked:
        return ("Research next: " + ", ".join(x.upper() for x in ranked) + ". "
                "Validate the specific learning or product need with target-language interviews and a small landing-page experiment. Measure qualified sign-ups and willingness to pay before investing in localization.")
    if result["priority"]["review_first"]:
        return ("No clear shortlist under the selected rule. Resolve coverage and comparability warnings first. "
                "Use target-language interviews to check the actual product need; these data alone do not justify a launch decision.")
    return ("No consistently positive signal under the selected rule. This is not proof of no demand. "
            "Use target-language interviews and a small landing-page experiment to check the actual product need before investing in localization.")


def charts(result, directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    from datetime import datetime
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(7.1, 3.45), sharex=True, constrained_layout=True)
    colors = ["#147d83", "#e17b30", "#6b59a8", "#bb4c69", "#407aaa"]
    dates = [datetime.strptime(m, "%Y-%m") for m in result["months"]]
    for i, series in enumerate(result["series"]):
        if not any(v is not None for v in series["views"]):
            continue
        y = [float('nan') if v is None else v for v in series["views"]]
        s = [float('nan') if v is None else v for v in series["share_per_million"]]
        label = series["language"].upper()
        axes[0].plot(dates, y, label=label, color=colors[i], linewidth=1.7, marker=".", markersize=3)
        axes[1].plot(dates, s, color=colors[i], linewidth=1.7, marker=".", markersize=3)
    axes[0].set_title("Monthly article views", loc="left", fontweight="bold", fontsize=10)
    axes[1].set_title("Article views per million project views", loc="left", fontweight="bold", fontsize=10)
    for ax in axes:
        ax.grid(axis="y", color="#e8ecee", linewidth=.7)
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 10 else f"{v:.1f}"))
        ax.tick_params(axis="both", labelsize=7)
    if axes[0].lines:
        axes[0].legend(frameon=False, loc="upper right", ncol=5, fontsize=8)
    else:
        axes[0].text(.5, .5, "No comparable observations available", ha="center", transform=axes[0].transAxes)
    fig.savefig(directory / "trend.png", dpi=180)
    fig.savefig(directory / "trend.svg")
    plt.close(fig)


def render(result, directory):
    import matplotlib
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    directory = Path(directory)
    charts(result, directory)
    fonts = Path(matplotlib.get_data_path()) / "fonts/ttf"
    pdfmetrics.registerFont(TTFont("WikiSans", str(fonts / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("WikiBold", str(fonts / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("WikiSans", normal="WikiSans", bold="WikiBold")
    width, height = A4
    margin, content_width = 34, width - 68
    c = canvas.Canvas(str(directory / "brief.pdf"), pagesize=A4)
    c.setTitle(f"Wikipedia interest: {result['topic']}")
    c.setAuthor("Wikipedia Interest Research")
    c.setFillColor(HexColor("#102b38"))
    c.rect(0, height - 116, width, 116, fill=1, stroke=0)
    c.setFillColor(HexColor("#78ded1"))
    c.setFont("WikiBold", 9)
    c.drawString(margin, height - 27, "WIKIPEDIA / AUDIENCE DISCOVERY")
    title = Paragraph(escape(result["topic"]), ParagraphStyle("title", fontName="WikiBold", fontSize=19, leading=23, textColor=HexColor("#ffffff")))
    _, h = title.wrap(content_width, 50)
    if h > 49:
        raise ResearchError("report_title_too_long", "Shorten --topic to fit a one-page report.")
    title.drawOn(c, margin, height - 40 - h)
    c.setFont("WikiSans", 8)
    c.setFillColor(HexColor("#d1e1e7"))
    c.drawString(margin, height - 100, f"{result['months'][0]} to {result['months'][-1]}  |  Complete UTC months  |  all-access / user")
    y = height - 133
    style = ParagraphStyle("body", fontName="WikiSans", fontSize=8, leading=11, textColor=HexColor("#203743"))
    small = ParagraphStyle("small", parent=style, fontSize=6.7, leading=9)

    def para(text, heading=False, tiny=False):
        nonlocal y
        s = small if tiny else style
        p = Paragraph(("<b>" + escape(text) + "</b>") if heading else escape(text), s)
        _, h = p.wrap(content_width, 1000)
        if y - h < 42:
            raise ResearchError("report_overflow", "The brief exceeds one page. Shorten the topic or scope note, or use fewer languages.")
        p.drawOn(c, margin, y - h)
        y -= h + (5 if heading else 4)

    para("1 / Evidence snapshot", heading=True)
    rows = [["Wiki", "Last 12m views", "Raw YoY", "Relative YoY", "Stability"]]
    for m in result["metrics"]:
        rows.append([m["language"].upper(), number(m["latest_12m_views"]), pct(m["yoy_pct"]), pct(m["normalized_yoy_pct"]), m["stability"]])
    table = Table(rows, colWidths=[42, 133, 95, 112, content_width - 382])
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "WikiSans"), ("FONTNAME", (0, 0), (-1, 0), "WikiBold"), ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e4f2ef")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f5f7f8"), HexColor("#ffffff")]), ("TEXTCOLOR", (0, 0), (-1, -1), HexColor("#203743")), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    _, h = table.wrap(content_width, 200)
    table.drawOn(c, margin, y - h)
    y -= h + 9
    chart_height = 229 if len(rows) <= 4 else 200
    c.drawImage(str(directory / "trend.png"), margin, y - chart_height, width=content_width, height=chart_height, preserveAspectRatio=True, anchor="c", mask="auto")
    y -= chart_height + 7
    para("2 / What the evidence supports", heading=True)
    for note in observations(result):
        para(note, tiny=len(result["metrics"]) > 3)
    para("3 / Next product check", heading=True)
    para("Criterion: " + result["priority"]["criterion"] + "; shortlist requires positive raw and relative growth without diagnostic flags.", tiny=True)
    para(next_step(result), tiny=len(result["metrics"]) > 3)
    para("Scope and limitations", heading=True)
    scope = "One current-title article per language. Title histories and redirect views are not merged. Language is not country; views are not people or purchase intent. Stability describes this series, not business success."
    if result.get("scope_note"):
        scope += " Scope: " + result["scope_note"]
    para(scope, tiny=True)
    if result.get("warnings"):
        descriptions = {"stale_cache_used_offline": "A saved snapshot was reused; freshness was not checked online.", "partial_API_failure: see metrics.json errors": "Some data could not be retrieved; affected comparisons are incomplete."}
        para("Data note: " + " ".join(descriptions.get(w, w) for w in result["warnings"]), tiny=True)
    para("Relative YoY = change in article share of project traffic. YoY uses the final 12 months vs the preceding 12. Gaps are missing data, never imputed zeros.", tiny=True)
    para("Articles and coverage", heading=True)
    for page, metric in zip(result["pages"], result["metrics"]):
        text = f"{page['language'].upper()}: {page.get('title', 'no verified equivalent')} | {metric['observed_months']}/{metric['expected_months']} observed months"
        para(text, tiny=True)
        if page.get("url"):
            c.linkURL(page["url"], (margin, y + 3, width - margin, y + 13), relative=0)
    c.setStrokeColor(HexColor("#cfdbdf"))
    c.line(margin, 34, width - margin, 34)
    c.setFont("WikiSans", 6)
    c.setFillColor(HexColor("#526874"))
    c.drawString(margin, 23, f"Wikimedia Analytics API (CC0) + Wikidata | {result['created_at'][:10]} | Method {result['method_version']}")
    c.drawRightString(width - margin, 23, "Audit: manifest.json / sources.json / metrics.json")
    c.linkURL("https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html", (margin, 20, 255, 31), relative=0)
    c.save()
    md = [f"# {result['topic']}", "", f"Period: {result['months'][0]} to {result['months'][-1]} (complete UTC months).", "", "| Wiki | Last 12m views | Raw YoY | Relative YoY | Stability |", "|---|---:|---:|---:|---|"]
    md += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    md += ["", *observations(result), "", next_step(result), "", scope, "", "## Articles"]
    md += [f"- {p['language']}: [{p.get('title', 'missing')}]({p.get('url', '')}); mapping={p['mapping']}; status={p['status']}" for p in result["pages"]]
    md += ["", "## Criteria", result["priority"]["rule"], "", "Source URLs, fetch timestamps, checksums and response bodies are recorded in sources.json and sources/. No inferred explanations of spikes are asserted as facts."]
    (directory / "brief.md").write_text("\n".join(md) + "\n", encoding="utf-8")
