"""
pdf_reporter — Rapport PDF v7.0 — §19
Sections : KPIs · 3 sections par Tier · AI · Fleet.

Pipeline : SpcService → graphiques matplotlib → HTML Jinja2 → PDF WeasyPrint.

GR-09 : peut être appelé depuis un thread daemon.
Imports lourds (matplotlib/jinja2/weasyprint) sont lazy pour permettre
l'import du module même quand ces dépendances manquent.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Localisation du template
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TEMPLATE_DIR  = os.path.join(os.path.dirname(__file__), "report_templates")
_DEFAULT_TEMPLATE_NAME = "inspection_report_v7.html"


class SpcServiceProto(Protocol):
    def compute_spc(
        self,
        product_id : str,
        n          : int = 100,
        period_hours: Optional[float] = None,
    ) -> Any: ...


class DatabaseProto(Protocol):
    def get_history(self, limit: int, product_id: Optional[str]) -> list[Any]: ...


class FleetHistoryProto(Protocol):
    def list_imports(self) -> list[dict]: ...


# ─────────────────────────────────────────────────────────────────────────────
#  PDFReporter
# ─────────────────────────────────────────────────────────────────────────────

class PDFReporter:
    """
    Génère le rapport PDF v7.0 d'inspection — §19.
    """

    def __init__(
        self,
        spc_service   : SpcServiceProto,
        database      : DatabaseProto,
        fleet_history : Optional[FleetHistoryProto] = None,
        template_dir  : Optional[str] = None,
        template_name : str           = _DEFAULT_TEMPLATE_NAME,
        output_dir    : Optional[str] = None,
    ) -> None:
        self._spc           = spc_service
        self._db            = database
        self._fleet_history = fleet_history
        self._template_dir  = template_dir or _DEFAULT_TEMPLATE_DIR
        self._template_name = template_name
        self._output_dir    = output_dir or os.path.join("data", "reports")
        os.makedirs(self._output_dir, exist_ok=True)
        self._registry: dict[str, str] = {}

    # ── API publique ─────────────────────────────────────────────────────────

    def generate(
        self,
        product_id    : Optional[str] = None,
        period_hours  : float         = 24.0,
        n             : int           = 100,
        output_path   : Optional[str] = None,
        report_id     : Optional[str] = None,
    ) -> str:
        """
        Génère un rapport PDF, retourne `report_id`.
        Le chemin est consultable via `get_pdf_path(report_id)`.
        """
        rid          = report_id or f"rpt-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        pdf_path     = output_path or os.path.join(self._output_dir, f"{rid}.pdf")
        spc          = self._spc.compute_spc(
            product_id   = product_id or "",
            n            = n,
            period_hours = period_hours,
        )
        results      = self._db.get_history(limit=n, product_id=product_id) or []
        fleet_imports= []
        if self._fleet_history is not None:
            try:
                fleet_imports = list(self._fleet_history.list_imports() or [])
            except Exception as e:
                logger.warning("Fleet history indisponible : %s", e)

        charts = self._build_charts(spc, results)
        html   = self._render_html(
            spc=spc,
            charts=charts,
            results=results,
            fleet_imports=fleet_imports,
            product_id=product_id or "",
            period_hours=period_hours,
        )
        self._render_pdf(html, pdf_path)
        self._registry[rid] = pdf_path
        logger.info("Rapport PDF généré : %s", pdf_path)
        return rid

    def get_pdf_path(self, report_id: str) -> Optional[str]:
        return self._registry.get(report_id)

    # ── Graphiques (matplotlib · base64 PNG) ─────────────────────────────────

    def _build_charts(self, spc: Any, results: list[Any]) -> dict[str, str]:
        """
        Renvoie {nom_chart: data-uri PNG base64}. Vide si matplotlib indispo.
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib indisponible — graphiques désactivés")
            return {}

        charts: dict[str, str] = {}
        tier_keys = ("CRITICAL", "MAJOR", "MINOR")

        # 1) Distribution fails par Tier (barplot)
        fig, ax = plt.subplots(figsize=(6, 3.5))
        labels  = list(tier_keys)
        values  = [int(spc.fail_distribution.get(k, 0)) for k in tier_keys]
        colors  = ["#FF4444", "#FF8800", "#FFCC00"]
        ax.bar(labels, values, color=colors, edgecolor="black")
        ax.set_title("Fails par Tier")
        ax.set_ylabel("Nombre")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        charts["fail_distribution"] = _fig_to_data_uri(fig, plt)

        # 2) X-bar chart par Tier
        for tier_key in tier_keys:
            stats = spc.tier_stats.get(tier_key)
            if stats is None or not stats.xbar:
                continue
            fig, ax = plt.subplots(figsize=(6, 3.0))
            xs = list(range(1, len(stats.xbar) + 1))
            ax.plot(xs, list(stats.xbar), marker="o", color="#1f77b4", label="X-bar")
            ax.axhline(stats.ucl_xbar, color="red",   linestyle="--", label="UCL")
            ax.axhline(stats.lcl_xbar, color="red",   linestyle="--", label="LCL")
            ax.axhline(stats.mean,     color="green", linestyle="-",  label="mean")
            ax.set_title(f"X-bar — Tier {tier_key}")
            ax.set_xlabel("Sous-groupe")
            ax.set_ylabel("Score moyen")
            ax.set_ylim(0.0, 1.05)
            ax.grid(linestyle="--", alpha=0.4)
            ax.legend(loc="lower right", fontsize=8)
            charts[f"xbar_{tier_key.lower()}"] = _fig_to_data_uri(fig, plt)

        # 3) Tier scores over time (ligne)
        if results:
            fig, ax = plt.subplots(figsize=(6, 3.0))
            xs = list(range(1, len(results) + 1))
            for tier_key, color in zip(tier_keys, colors):
                ys = [
                    float((getattr(r, "tier_scores", {}) or {}).get(tier_key, float("nan")))
                    for r in results
                ]
                ax.plot(xs, ys, marker=".", color=color, label=tier_key)
            ax.set_title("Tier scores au fil des inspections")
            ax.set_xlabel("Inspection #")
            ax.set_ylabel("Score")
            ax.set_ylim(0.0, 1.05)
            ax.grid(linestyle="--", alpha=0.4)
            ax.legend(loc="lower right", fontsize=8)
            charts["scores_timeseries"] = _fig_to_data_uri(fig, plt)

        return charts

    # ── HTML (Jinja2) ────────────────────────────────────────────────────────

    def _render_html(
        self,
        spc           : Any,
        charts        : dict[str, str],
        results       : list[Any],
        fleet_imports : list[dict],
        product_id    : str,
        period_hours  : float,
    ) -> str:
        try:
            import jinja2
        except ImportError as e:
            raise RuntimeError(
                "jinja2 non installé — pip install jinja2"
            ) from e

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self._template_dir),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        try:
            tpl = env.get_template(self._template_name)
        except jinja2.TemplateNotFound:
            logger.warning(
                "Template %s introuvable dans %s — utilisation du fallback",
                self._template_name, self._template_dir,
            )
            tpl = jinja2.Template(_FALLBACK_TEMPLATE)

        # Observers : moyenne & fails par observer_id
        observer_stats = _aggregate_observer_stats(results)

        # Fails par Tier (verbose : produit_id + fail_reasons)
        tier_fails = _collect_tier_fails(results)

        return tpl.render(
            product_id        = product_id,
            period_hours      = period_hours,
            generated_at      = time.strftime("%Y-%m-%d %H:%M:%S"),
            total             = spc.total,
            ok_count          = spc.ok_count,
            nok_count         = spc.nok_count,
            review_count      = spc.review_count,
            conformity_rate   = round(_conformity_rate(spc) * 100, 2),
            tier_stats        = _serialize_tier_stats(spc.tier_stats),
            fail_distribution = spc.fail_distribution,
            tier_fails        = tier_fails,
            observer_stats    = observer_stats,
            fleet_imports     = fleet_imports,
            charts            = charts,
        )

    # ── PDF (WeasyPrint) ─────────────────────────────────────────────────────

    def _render_pdf(self, html: str, pdf_path: str) -> None:
        try:
            import weasyprint
        except ImportError:
            logger.warning("weasyprint indisponible — sortie HTML brute")
            html_path = pdf_path[:-4] + ".html" if pdf_path.endswith(".pdf") else pdf_path + ".html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            # On tente quand même un PDF "stub" pour respecter l'API.
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4\n% weasyprint indisponible - see .html sidecar\n")
            return

        weasyprint.HTML(string=html).write_pdf(pdf_path)


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _fig_to_data_uri(fig: Any, plt: Any) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _conformity_rate(spc: Any) -> float:
    rate = getattr(spc, "conformity_rate", None)
    if rate is not None:
        return float(rate)
    return (spc.ok_count / spc.total) if spc.total else 0.0


def _serialize_tier_stats(tier_stats: dict[str, Any]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, stats in tier_stats.items():
        if is_dataclass(stats):
            d = asdict(stats)
            d["tier"] = key
            out[key] = d
        else:
            out[key] = dict(getattr(stats, "__dict__", {}))
    return out


def _collect_tier_fails(results: list[Any]) -> dict[str, list[dict]]:
    """{tier: [{frame_id, product_id, fail_reasons}]} pour les FinalResult NOK."""
    out: dict[str, list[dict]] = {"CRITICAL": [], "MAJOR": [], "MINOR": []}
    for r in results:
        if _enum_value(getattr(r, "verdict", None)) != "NOK":
            continue
        tier = _enum_value(getattr(r, "fail_tier", None))
        if tier not in out:
            continue
        out[tier].append({
            "frame_id":     getattr(r, "frame_id", ""),
            "product_id":   getattr(r, "product_id", ""),
            "fail_reasons": list(getattr(r, "fail_reasons", []) or []),
            "timestamp":    getattr(r, "timestamp", None),
        })
    return out


def _aggregate_observer_stats(results: list[Any]) -> list[dict]:
    """
    Agrège : observer_id → mean(value), fails count.
    Tolérant aux résultats sans signals.
    """
    acc : dict[str, dict[str, Any]] = {}
    for r in results:
        for tier_key, tv in (getattr(r, "tier_verdicts", {}) or {}).items():
            for sig in getattr(tv, "signals", ()) or ():
                obs_id = getattr(sig, "observer_id", None) or "unknown"
                bucket = acc.setdefault(obs_id, {"values": [], "fails": 0})
                value  = getattr(sig, "value", None)
                if value is not None:
                    try:
                        bucket["values"].append(float(value))
                    except (TypeError, ValueError):
                        pass
                if not bool(getattr(sig, "passed", True)):
                    bucket["fails"] += 1

    out: list[dict] = []
    for obs_id, b in sorted(acc.items()):
        vals = b["values"]
        out.append({
            "observer_id": obs_id,
            "mean_value" : round(sum(vals) / len(vals), 4) if vals else 0.0,
            "samples"    : len(vals),
            "fail_count" : b["fails"],
        })
    return out


def _enum_value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


# ═════════════════════════════════════════════════════════════════════════════
#  Template fallback (si inspection_report_v7.html absent)
# ═════════════════════════════════════════════════════════════════════════════

_FALLBACK_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>IVS v7.0 Report (fallback)</title></head>
<body>
  <h1>TS2I IVS v7.0 — Rapport (template fallback)</h1>
  <p>Produit : {{ product_id }} · Période : {{ period_hours }}h · Généré : {{ generated_at }}</p>
  <p>Total : {{ total }} · OK : {{ ok_count }} · NOK : {{ nok_count }} · REVIEW : {{ review_count }}
     · Taux : {{ conformity_rate }}%</p>
  <h2>Tier stats</h2>
  <ul>
  {% for k, s in tier_stats.items() %}
    <li>{{ k }} : Cp={{ '%.2f' % s.cp }} Cpk={{ '%.2f' % s.cpk }} samples={{ s.samples }} fails={{ s.fail_count }}</li>
  {% endfor %}
  </ul>
</body></html>
"""
