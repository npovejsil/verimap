"""Country archetypes: descriptive clusters, not causal types.

KMeans on a handful of standardized latest-year indicators, for ~200 rows.
Reports silhouette score across a range of k so the choice of k is
inspectable rather than asserted, and returns cluster labels as plain
integers -- any narrative label ("energy-poor", "renewables leader") is a
human judgment applied after looking at the cluster centers, not something
the algorithm knows.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ArchetypeResult:
    labels: pd.Series  # place_dcid -> cluster int
    # cluster -> mean of each input column (original scale)
    cluster_centers: pd.DataFrame
    silhouette_by_k: dict[int, float]
    k_used: int


def _silhouette_scan(x_scaled, k_range: range) -> dict[int, float]:
    scores: dict[int, float] = {}
    for k in k_range:
        if k >= len(x_scaled):
            continue
        labels = KMeans(n_clusters=k, random_state=0, n_init=10).fit_predict(x_scaled)
        if len(set(labels)) < 2:
            continue
        scores[k] = float(silhouette_score(x_scaled, labels))
    return scores


def compute_archetypes(
    df: pd.DataFrame,
    feature_cols: list[str],
    k: int | None = None,
    k_range: range = range(2, 7),
    place_col: str = "place_dcid",
    random_state: int = 0,
) -> ArchetypeResult | None:
    """Cluster places on standardized feature columns.

    If `k` is None, picks the k in `k_range` with the highest silhouette
    score. Returns None if fewer rows than the smallest k in `k_range`, or
    if any feature column is entirely missing.
    """
    clean = df.dropna(subset=feature_cols + [place_col]).copy()
    if len(clean) < k_range.start:
        return None

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(clean[feature_cols])

    if k is None:
        scores = _silhouette_scan(x_scaled, k_range)
        if not scores:
            return None
        k = max(scores, key=scores.get)
    else:
        scores = _silhouette_scan(x_scaled, range(k, k + 1))

    model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = model.fit_predict(x_scaled)

    clean["_cluster"] = labels
    centers = clean.groupby("_cluster")[feature_cols].mean()

    return ArchetypeResult(
        labels=pd.Series(labels, index=clean[place_col].values),
        cluster_centers=centers,
        silhouette_by_k=scores,
        k_used=k,
    )
