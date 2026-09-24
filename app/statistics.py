from statistics import fmean, pstdev


def score_statistics(generations):
    """Describe all saved scores in this session, including zero ratings."""
    scores = [g["score"] for g in generations if g["score"] is not None]
    return {
        "count": len(scores),
        "mean": fmean(scores) if scores else None,
        "best": max(scores) if scores else None,
        "standard_deviation": pstdev(scores) if len(scores) >= 2 else None,
    }
