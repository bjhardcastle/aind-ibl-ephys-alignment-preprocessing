"""Internal constants for the preprocessing pipeline."""

from __future__ import annotations

_BLESSED_DIRECTION: str = "IRP"
"""DICOM orientation code expected by the IBL ephys alignment GUI."""

REGISTRATION_TRANSFORMS: tuple[str, ...] = (
    "ls_to_template_SyN_0GenericAffine.mat",
    "ls_to_template_SyN_1InverseWarp.nii.gz",
)
"""Transforms a registration directory must supply, whichever asset it lives in.

These are the individual->template half of the *point* chain, which is also what
resamples CCF volumes into image space. The forward warp is deliberately absent:
only the QC channels->CCF warp needs it, and standalone registrations are not
required to ship it.
"""

CONVERSION_METRICS: dict[str, tuple[str, str]] = {
    "raw_activity": ("aind_ephys_ibl_gui_conversion.activity", "raw_activity"),
}
"""Optional conversion metric extensions, keyed by pipeline-facing name.

Each value names the ``aind_ephys_ibl_gui_conversion`` module and factory that
configure the metric for ``extract_continuous(extra_metrics=...)``. Modules are
imported only when a run requests the metric, so conversion releases without
it still work for runs that do not.
"""
