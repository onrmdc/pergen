"""
``ReportService`` — façade over the report repository plus the
``compare_runs`` helper that pre/post diff endpoints share.
"""
from __future__ import annotations

from backend.repositories import ReportRepository


class ReportService:
    """Pre/post check report operations."""

    def __init__(self, report_repo: ReportRepository) -> None:
        self._repo = report_repo

    def list(self, actor: str | None = None) -> list[dict]:
        return self._repo.list(actor=actor)

    def load(self, run_id: str, actor: str | None = None) -> dict | None:
        return self._repo.load(run_id, actor=actor)

    def save(
        self,
        *,
        run_id: str,
        name: str,
        created_at: str,
        devices: list[dict],
        device_results: list[dict],
        post_created_at: str | None = None,
        post_device_results: list[dict] | None = None,
        comparison: dict | None = None,
        created_by_actor: str | None = None,
    ) -> None:
        self._repo.save(
            run_id=run_id,
            name=name,
            created_at=created_at,
            devices=devices,
            device_results=device_results,
            post_created_at=post_created_at,
            post_device_results=post_device_results,
            comparison=comparison,
            created_by_actor=created_by_actor,
        )

    def delete(self, run_id: str, actor: str | None = None) -> bool:
        return self._repo.delete(run_id, actor=actor)

    # ------------------------------------------------------------------ #
    # Pre/post comparison                                                #
    # ------------------------------------------------------------------ #
    @staticmethod
    def compare_runs(
        pre_results: list[dict], post_results: list[dict]
    ) -> list[dict]:
        """Per-device key-by-key diff of two ``parsed_flat`` payloads.

        Returns a list of ``{hostname, ip, diff}`` entries. ``diff`` maps
        each changed key to ``{"pre": <pre value>, "post": <post value>}``.
        Pairing is positional — caller must ensure both lists are aligned
        device-for-device (which is what the legacy app.py code did).
        """
        comparison: list[dict] = []
        for pre_r, post_r in zip(pre_results, post_results, strict=False):
            pre_flat = pre_r.get("parsed_flat") or {}
            post_flat = post_r.get("parsed_flat") or {}
            diff: dict = {}
            for k in set(pre_flat) | set(post_flat):
                pv, pov = pre_flat.get(k), post_flat.get(k)
                if pv != pov:
                    diff[k] = {"pre": pv, "post": pov}
            comparison.append(
                {
                    "hostname": pre_r.get("hostname"),
                    "ip": pre_r.get("ip"),
                    "diff": diff,
                }
            )
        return comparison
