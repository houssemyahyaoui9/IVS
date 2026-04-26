"""
exceptions — TS2I IVS v7.0
Hiérarchie d'exceptions personnalisées v7.0
"""


class ConfigValidationError(ValueError):
    """Config.yaml invalide ou paramètre produit hors contraintes."""


class ObserverError(RuntimeError):
    """Erreur interne d'un AI Observer (GR-11 : jamais avalée silencieusement)."""


class RuleEngineError(RuntimeError):
    """Erreur logique dans RuleEngine (ne devrait jamais arriver — GR-08)."""


class TierOrchestratorError(RuntimeError):
    """Erreur d'orchestration des 3 Tiers."""


class PipelineTimeoutError(RuntimeError):
    """Timeout pipeline dépassé (watchdog §18.1)."""


class CameraError(RuntimeError):
    """Erreur caméra (acquisition, déconnexion, résolution non supportée)."""


class SystemStateError(RuntimeError):
    """Transition FSM illégale — §4 tableau des transitions autorisées."""


class CalibrationError(RuntimeError):
    """Erreur lors de la calibration 7 étapes — §10."""


class AlignmentError(RuntimeError):
    """Alignement SIFT échoué — good_matches insuffisants ou homographie nulle."""


class FleetImportError(RuntimeError):
    """
    Échec de l'import d'un package Fleet (.ivs) — GR-13.
    Levée pour signature corrompue, version incompatible, validation
    ModelValidator échouée, ou import concurrent (réseau/USB).
    """
