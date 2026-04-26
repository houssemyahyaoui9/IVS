"""
models — TS2I IVS v7.0
Tous les frozen dataclasses v7.0 — §5
GR-07 : FinalResult immuable après création
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.exceptions import ConfigValidationError
from core.tier_result import TierLevel, TierVerdict


# ─────────────────────────────────────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────────────────────────────────────

class SeverityLevel(Enum):
    """
    Gravité du défaut — dérivée du Tier ayant échoué (CLAUDE.md mapping).
    CRITICAL fail → REJECT
    MAJOR fail    → DEFECT_1
    MINOR mandatory fail → DEFECT_2
    MINOR non-mandatory / REVIEW → REVIEW
    All pass + scores > 0.90 → EXCELLENT
    All pass → ACCEPTABLE
    """
    EXCELLENT  = "EXCELLENT"
    ACCEPTABLE = "ACCEPTABLE"
    REVIEW     = "REVIEW"
    DEFECT_2   = "DEFECT_2"
    DEFECT_1   = "DEFECT_1"
    REJECT     = "REJECT"


class SystemState(Enum):
    """FSM — 9 états §4"""
    IDLE_NO_PRODUCT = "IDLE_NO_PRODUCT"
    IMAGE_CAPTURE   = "IMAGE_CAPTURE"
    CALIBRATING     = "CALIBRATING"
    TRAINING        = "TRAINING"
    IDLE_READY      = "IDLE_READY"
    RUNNING         = "RUNNING"
    REVIEW          = "REVIEW"
    ERROR           = "ERROR"
    SHUTTING_DOWN   = "SHUTTING_DOWN"


class SwitchResult(Enum):
    """Résultat d'un changement de produit actif."""
    SUCCESS        = "SUCCESS"
    FAILED         = "FAILED"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"


class LearningDecision(Enum):
    """Décision des gates d'apprentissage autonome — §11."""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER  = "DEFER"


# ─────────────────────────────────────────────────────────────────────────────
#  Primitives physiques / caméra
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PhysicalDimensions:
    """Dimensions réelles d'un produit en mm."""
    width_mm  : float
    height_mm : float

    def __post_init__(self) -> None:
        if self.width_mm <= 0:
            raise ConfigValidationError(
                f"PhysicalDimensions.width_mm={self.width_mm} doit être > 0"
            )
        if self.height_mm <= 0:
            raise ConfigValidationError(
                f"PhysicalDimensions.height_mm={self.height_mm} doit être > 0"
            )


@dataclass(frozen=True)
class CameraResolution:
    """Résolution caméra en pixels."""
    width  : int
    height : int

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ConfigValidationError(
                f"CameraResolution.width={self.width} doit être > 0"
            )
        if self.height <= 0:
            raise ConfigValidationError(
                f"CameraResolution.height={self.height} doit être > 0"
            )


@dataclass(frozen=True)
class BoundingBox:
    """
    Boîte englobante en coordonnées mm (ou pixels si issu de YOLO).
    to_pixel() convertit des mm vers pixels via pixel_per_mm.
    """
    x : float   # coin haut-gauche X
    y : float   # coin haut-gauche Y
    w : float   # largeur
    h : float   # hauteur

    def __post_init__(self) -> None:
        if self.w <= 0:
            raise ConfigValidationError(
                f"BoundingBox.w={self.w} doit être > 0"
            )
        if self.h <= 0:
            raise ConfigValidationError(
                f"BoundingBox.h={self.h} doit être > 0"
            )

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def to_pixel(self, pixel_per_mm: float) -> BoundingBox:
        if pixel_per_mm <= 0:
            raise ConfigValidationError(
                f"pixel_per_mm={pixel_per_mm} doit être > 0"
            )
        return BoundingBox(
            x=self.x * pixel_per_mm,
            y=self.y * pixel_per_mm,
            w=self.w * pixel_per_mm,
            h=self.h * pixel_per_mm,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Résultats de modules
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LuminosityResult:
    """
    Résultat du contrôle de luminosité — §18.3 LuminosityChecker.
    Produit par S2 avant tout traitement AI.
    """
    value         : float   # luminosité moyenne mesurée [0, 255]
    ref_mean      : float   # référence calibrée (étape 2 §10)
    delta_percent : float   # écart relatif en %
    ok            : bool
    warning       : bool    # delta > warning_percent (15%)
    critical      : bool    # delta > critical_percent (30%)

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 255.0):
            raise ValueError(
                f"LuminosityResult.value={self.value} hors [0, 255]"
            )
        if self.delta_percent < 0.0:
            raise ValueError(
                f"LuminosityResult.delta_percent={self.delta_percent} < 0"
            )

    @property
    def severity(self) -> str:
        """'CRITICAL' | 'WARNING' | 'OK' — dérivé des booleans (§18.3)."""
        if self.critical:
            return "CRITICAL"
        if self.warning:
            return "WARNING"
        return "OK"


@dataclass(frozen=True)
class LLMExplanation:
    """
    Explication générée par LLM Mistral 7B — §16.
    Display only — jamais utilisée dans la logique de décision (GR-04).
    fail_tier     : tier ayant échoué ("CRITICAL"|"MAJOR"|"MINOR"|"NONE")
    fallback_used : True si LLM indisponible/timeout, explication textuelle utilisée
    """
    summary        : str
    defect_detail  : str
    probable_cause : str
    recommendation : str
    latency_ms     : float
    fail_tier      : str   = "NONE"   # "CRITICAL" | "MAJOR" | "MINOR" | "NONE"
    fallback_used  : bool  = True
    generated_at   : float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.latency_ms < 0.0:
            raise ValueError(
                f"LLMExplanation.latency_ms={self.latency_ms} < 0"
            )
        if self.fail_tier not in {"CRITICAL", "MAJOR", "MINOR", "NONE"}:
            raise ValueError(
                f"LLMExplanation.fail_tier='{self.fail_tier}' invalide"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  Règles produit
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CriterionRule:
    """
    Règle d'un critère défini par l'utilisateur — §5.4
    mandatory=False + tier=MINOR → REVIEW si non validé.
    details : paramètres observer-spécifiques (ex : expected_pattern, barcode_zone).
              Exclu du hash/compare pour conserver la hashabilité du dataclass.
    """
    criterion_id : str
    label        : str
    tier         : TierLevel
    observer_id  : str
    threshold    : float
    enabled      : bool
    mandatory    : bool
    details      : dict = field(default_factory=dict, hash=False, compare=False)

    def __post_init__(self) -> None:
        if not self.criterion_id:
            raise ConfigValidationError("CriterionRule.criterion_id vide")
        if not self.observer_id:
            raise ConfigValidationError("CriterionRule.observer_id vide")
        if self.threshold < 0.0:
            raise ConfigValidationError(
                f"CriterionRule.threshold={self.threshold} doit être >= 0"
            )


@dataclass(frozen=True)
class ProductRules:
    """
    Ensemble des règles produit — §5.4
    Chargé à l'init, jamais modifié pendant RUNNING (GR-12).
    """
    product_id : str
    criteria   : tuple[CriterionRule, ...]

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ConfigValidationError("ProductRules.product_id vide")

    @property
    def critical_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.CRITICAL)

    @property
    def major_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.MAJOR)

    @property
    def minor_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.MINOR)

    def criteria_for_tier(self, tier: TierLevel) -> tuple[CriterionRule, ...]:
        if tier == TierLevel.CRITICAL:
            return self.critical_criteria
        elif tier == TierLevel.MAJOR:
            return self.major_criteria
        return self.minor_criteria


# ─────────────────────────────────────────────────────────────────────────────
#  Définition produit
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LogoDefinition:
    """
    Définition d'un logo à inspecter — §37 hérité v6.1.
    Un produit peut avoir 0..N logos.
    """
    logo_id       : str
    name          : str
    expected_zone : BoundingBox   # zone attendue en mm
    class_name    : str           # classe YOLO à détecter
    tolerance_mm  : float         # tolérance de position en mm

    def __post_init__(self) -> None:
        if not self.logo_id:
            raise ConfigValidationError("LogoDefinition.logo_id vide")
        if not self.class_name:
            raise ConfigValidationError("LogoDefinition.class_name vide")
        if self.tolerance_mm < 0.0:
            raise ConfigValidationError(
                f"LogoDefinition.tolerance_mm={self.tolerance_mm} doit être >= 0"
            )


@dataclass(frozen=True)
class ProductDefinition:
    """
    Définition complète d'un produit v7.0.
    Inclut logo_definitions et product_barcode (nouveautés v7.0).
    """
    product_id       : str
    name             : str
    version          : str
    width_mm         : float
    height_mm        : float
    logo_definitions : tuple[LogoDefinition, ...]
    product_barcode  : Optional[str]       = None
    station_id       : str                 = "STATION-001"

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ConfigValidationError("ProductDefinition.product_id vide")
        if not self.name:
            raise ConfigValidationError("ProductDefinition.name vide")
        if self.width_mm <= 0:
            raise ConfigValidationError(
                f"ProductDefinition.width_mm={self.width_mm} doit être > 0"
            )
        if self.height_mm <= 0:
            raise ConfigValidationError(
                f"ProductDefinition.height_mm={self.height_mm} doit être > 0"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  Résultat final d'inspection
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FinalResult:
    """
    Résultat complet d'une inspection v7.0 — §5.3
    Immuable après création — GR-07.
    """
    # Identité
    frame_id        : str
    product_id      : str
    model_versions  : dict[str, str]            # {"yolo": "v3", ...}

    # Verdict principal (Tier-based)
    verdict         : str                       # "OK" | "NOK" | "REVIEW"
    severity        : SeverityLevel
    fail_tier       : Optional[TierLevel]
    fail_reasons    : tuple[str, ...]

    # Verdicts et scores par Tier
    tier_verdicts   : dict[str, TierVerdict]    # {"CRITICAL": ..., ...}
    tier_scores     : dict[str, float]          # {"CRITICAL": 0.94, ...}

    # Explication LLM (display only — GR-04)
    llm_explanation : Optional[LLMExplanation]

    # Métadonnées
    pipeline_ms         : float
    background_complete : bool
    luminosity_result   : LuminosityResult
    timestamp           : float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.verdict not in {"OK", "NOK", "REVIEW"}:
            raise ValueError(
                f"FinalResult.verdict='{self.verdict}' invalide"
                " — doit être 'OK', 'NOK' ou 'REVIEW'"
            )
        if self.pipeline_ms < 0.0:
            raise ValueError(
                f"FinalResult.pipeline_ms={self.pipeline_ms} doit être >= 0"
            )
        if not self.tier_verdicts:
            raise ValueError(
                "FinalResult.tier_verdicts ne peut pas être vide"
            )
        if "CRITICAL" not in self.tier_verdicts:
            raise ValueError(
                "FinalResult.tier_verdicts doit contenir 'CRITICAL'"
            )
        for key, tv in self.tier_verdicts.items():
            if not isinstance(tv, TierVerdict):
                raise ValueError(
                    f"FinalResult.tier_verdicts['{key}'] n'est pas un TierVerdict"
                )


# ─────────────────────────────────────────────────────────────────────────────
#  Snapshot système (émis via UIBridge.system_snapshot)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SystemSnapshot:
    """
    Photo instantanée de l'état système émise périodiquement via UIBridge.
    Display only — jamais utilisée dans la logique de décision.
    """
    state             : "SystemState"
    active_product_id : Optional[str]
    ok_count          : int
    nok_count         : int
    review_count      : int
    timestamp         : float = field(default_factory=time.time)
