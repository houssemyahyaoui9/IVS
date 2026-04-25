"""
ExecutionGuard — GR-11 : aucun stage ne retourne None
Si un stage lève une exception → ErrorResult (jamais None, jamais silencieux)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from pipeline.frames import ErrorResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ExecutionGuard:
    """
    Enveloppe les appels de stages pour garantir GR-11.

    Usage :
        result = ExecutionGuard.run(stage.process, input_data, "S2_PreProcess")
        if isinstance(result, ErrorResult):
            # gérer l'erreur proprement
    """

    @staticmethod
    def run(
        fn: Callable[..., T],
        *args: Any,
        stage_name: str,
        **kwargs: Any,
    ) -> T | ErrorResult:
        """
        Appelle fn(*args, **kwargs) et garantit une valeur non-None.

        Returns:
            Résultat de fn — ou ErrorResult si fn lève une exception ou retourne None.
        """
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            logger.exception("ExecutionGuard [%s] exception : %s", stage_name, exc)
            return ErrorResult(stage=stage_name, error_msg=str(exc))

        if result is None:
            msg = f"Stage {stage_name} a retourné None — violation GR-11"
            logger.error(msg)
            return ErrorResult(stage=stage_name, error_msg=msg)

        return result
