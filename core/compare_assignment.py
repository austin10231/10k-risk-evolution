"""Rectangular linear-assignment solver used by Compare.

We want the matching that maximises total similarity between two sets
of sub-risks. SciPy is not on the project's dependency list, so this
file ships a pure-Python Hungarian (Kuhn–Munkres) for the rectangular
minimum-cost case.

Inputs are small (typically <= 50 items per bucket) so an O(n^3)
implementation is plenty.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

INF = float("inf")


def _hungarian(cost: List[List[float]]) -> List[int]:
    """Return assignment[r] = c for each row r minimising sum(cost).

    Cost matrix must be padded to square with INF before calling.
    Implementation: O(n^3) Jonker-Volgenant via potentials, adapted
    from the classic competitive-programming sketch.
    """
    n = len(cost)
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0 != 0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    assignment = [-1] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def solve_assignment(
    score_matrix: Sequence[Sequence[float]],
    *,
    floor: float = 0.0,
) -> List[Tuple[int, int, float]]:
    """Return (row, col, score) tuples for the optimal maximum-weight
    matching across a rectangular score matrix.

    Pairs whose score is <= `floor` are dropped from the result so the
    caller doesn't have to re-check the threshold (the assignment may
    still output them when the matrix has many low-score cells).
    """
    if not score_matrix:
        return []
    rows = len(score_matrix)
    cols = len(score_matrix[0]) if rows else 0
    if cols == 0:
        return []

    n = max(rows, cols)
    # Convert to a cost matrix: cost = -score; pad with INF so dummy
    # rows/cols cannot beat real pairs.
    cost: List[List[float]] = []
    for r in range(n):
        row: List[float] = []
        for c in range(n):
            if r < rows and c < cols:
                row.append(-float(score_matrix[r][c]))
            else:
                row.append(0.0)  # dummies have cost 0; real edges < 0
        cost.append(row)

    assignment = _hungarian(cost)
    pairs: List[Tuple[int, int, float]] = []
    for r, c in enumerate(assignment):
        if r >= rows or c < 0 or c >= cols:
            continue
        score = float(score_matrix[r][c])
        if score <= floor:
            continue
        pairs.append((r, c, score))
    return pairs
