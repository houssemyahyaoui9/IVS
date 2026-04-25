"""
PipelineRunner — boucle principale d'inspection S1→S8
GR-05  : opérations Qt dans thread principal — pipeline dans thread dédié
GR-06  : config chargée une fois à l'init
GR-11  : ExecutionGuard enveloppe chaque stage
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Optional

from pipeline.execution_guard import ExecutionGuard
from pipeline.frames import AlignedFrame, ErrorResult, ProcessedFrame
from pipeline.stages.s1_acquisition import S1Acquisition
from pipeline.stages.s2_preprocessor import S2Preprocessor
from pipeline.stages.s3_alignment import S3Alignment
from pipeline.stages.s4_tier_orchestrator import S4TierOrchestratorStage
from pipeline.stages.s5_rule_engine_stage import S5RuleEngineStage
from pipeline.stages.s8_output import S8Output

if TYPE_CHECKING:
    from core.pipeline_controller import SystemController

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Thread d'inspection continue S1 → S2 → S3 → S4 → S5 → S8.

    Appelé par SystemController.start_inspection().
    Tourne dans un thread daemon séparé (GR-05).
    Chaque stage est protégé par ExecutionGuard (GR-11).
    """

    def __init__(
        self,
        s1: S1Acquisition,
        s2: S2Preprocessor,
        s3: S3Alignment,
        s4: S4TierOrchestratorStage,
        s5: S5RuleEngineStage,
        s8: S8Output,
        controller: "SystemController",
    ) -> None:
        self._s1         = s1
        self._s2         = s2
        self._s3         = s3
        self._s4         = s4
        self._s5         = s5
        self._s8         = s8
        self._controller = controller
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Contrôle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Lance le thread pipeline. Sans effet si déjà en cours."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("PipelineRunner: déjà en cours")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="PipelineRunner",
        )
        self._thread.start()
        logger.info("PipelineRunner: démarré")

    def request_stop(self) -> None:
        """Demande l'arrêt propre après la frame en cours."""
        self._stop_event.set()
        logger.info("PipelineRunner: arrêt demandé")

    def wait(self, timeout: float = 5.0) -> None:
        """Attend la fin du thread (pour tests / shutdown propre)."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ── Boucle principale ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Boucle d'inspection — une frame à la fois."""
        logger.info("PipelineRunner: boucle démarrée")
        while not self._stop_event.is_set():
            try:
                self._run_one_frame()
            except Exception as exc:
                logger.exception("PipelineRunner: erreur non gérée — %s", exc)
                self._controller.on_watchdog_triggered()
                break
        logger.info("PipelineRunner: boucle terminée")

    def _run_one_frame(self) -> None:
        """Exécute le pipeline complet sur une frame."""
        t_start = time.monotonic()

        # ── S1 : Acquisition ─────────────────────────────────────────────────
        raw = ExecutionGuard.run(self._s1.process, stage_name="S1_Acquisition")
        if isinstance(raw, ErrorResult):
            logger.error("S1 fail: %s", raw.error_msg)
            self._controller.on_watchdog_triggered()
            return
        # Notifier l'UI dès que la frame brute est disponible (live preview).
        self._controller.on_frame_acquired(raw)

        # ── S2 : PreProcess + Luminosité ──────────────────────────────────────
        proc = ExecutionGuard.run(self._s2.process, raw, stage_name="S2_Preprocessor")
        if isinstance(proc, ErrorResult):
            logger.error("S2 fail: %s", proc.error_msg)
            return
        assert isinstance(proc, ProcessedFrame)
        self._controller.on_luminosity_update(proc.luminosity)

        # ── S3 : Alignment ────────────────────────────────────────────────────
        aligned = ExecutionGuard.run(self._s3.process, proc, stage_name="S3_Alignment")
        if isinstance(aligned, ErrorResult):
            logger.error("S3 fail: %s", aligned.error_msg)
            return
        assert isinstance(aligned, AlignedFrame)

        # ── S4 : TierOrchestrator ─────────────────────────────────────────────
        orch_result = ExecutionGuard.run(
            self._s4.process, aligned, stage_name="S4_TierOrchestrator"
        )
        if isinstance(orch_result, ErrorResult):
            logger.error("S4 fail: %s", orch_result.error_msg)
            return

        # ── S5 : RuleEngine → FinalResult ─────────────────────────────────────
        pipeline_ms = (time.monotonic() - t_start) * 1000.0
        final = ExecutionGuard.run(
            self._s5.process,
            orch_result,
            proc.luminosity,
            pipeline_ms,
            stage_name="S5_RuleEngine",
        )
        if isinstance(final, ErrorResult):
            logger.error("S5 fail: %s", final.error_msg)
            return

        # ── Notifier le contrôleur ────────────────────────────────────────────
        self._controller.on_inspection_result(final)

        # ── S8 : Output (GPIO + DB + WS + Learning + LLM) ────────────────────
        ExecutionGuard.run(self._s8.process, final, stage_name="S8_Output")
