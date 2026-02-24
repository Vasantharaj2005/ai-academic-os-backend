"""
Bloom's Taxonomy Classifier.
Classifies learning outcomes and questions by Bloom's level.
"""

import re
from typing import Dict, List, Tuple


BLOOM_VERBS: Dict[str, List[str]] = {
    "remember": [
        "define", "list", "recall", "recognize", "state", "identify",
        "name", "repeat", "reproduce", "describe", "label", "memorize",
    ],
    "understand": [
        "explain", "summarize", "paraphrase", "classify", "interpret",
        "compare", "discuss", "describe", "outline", "review", "translate",
    ],
    "apply": [
        "apply", "demonstrate", "use", "implement", "solve", "execute",
        "perform", "produce", "construct", "compute", "develop", "illustrate",
    ],
    "analyze": [
        "analyze", "differentiate", "examine", "break down", "distinguish",
        "compare", "contrast", "infer", "relate", "deconstruct", "investigate",
    ],
    "evaluate": [
        "evaluate", "judge", "critique", "assess", "justify", "argue",
        "defend", "prioritize", "recommend", "select", "support", "value",
    ],
    "create": [
        "create", "design", "build", "compose", "develop", "formulate",
        "generate", "plan", "produce", "propose", "construct", "devise",
    ],
}

BLOOM_WEIGHTS = {
    "remember": 1,
    "understand": 2,
    "apply": 3,
    "analyze": 4,
    "evaluate": 5,
    "create": 6,
}


class BloomClassifier:
    """
    Classifies text (learning outcomes, exam questions) by Bloom's taxonomy level.
    """

    def classify(self, text: str) -> Tuple[str, float]:
        """
        Classify text into a Bloom's taxonomy level.
        Returns (level, confidence).
        """
        text_lower = text.lower()
        scores: Dict[str, int] = {level: 0 for level in BLOOM_VERBS}

        for level, verbs in BLOOM_VERBS.items():
            for verb in verbs:
                if re.search(r"\b" + re.escape(verb) + r"\b", text_lower):
                    scores[level] += 1

        best_level = max(scores, key=lambda k: (scores[k], BLOOM_WEIGHTS[k]))
        total = sum(scores.values())
        confidence = scores[best_level] / total if total > 0 else 0.5

        return best_level, round(confidence, 2)

    def classify_batch(self, texts: List[str]) -> List[Dict]:
        """Classify multiple texts."""
        results = []
        for text in texts:
            level, confidence = self.classify(text)
            results.append({
                "text": text,
                "bloom_level": level,
                "confidence": confidence,
                "level_number": BLOOM_WEIGHTS[level],
            })
        return results

    def analyze_distribution(self, outcomes: List[str]) -> Dict[str, int]:
        """Get distribution of Bloom's levels across outcomes."""
        distribution = {level: 0 for level in BLOOM_VERBS}
        for text in outcomes:
            level, _ = self.classify(text)
            distribution[level] += 1
        return distribution

    def validate_higher_order_thinking(self, outcomes: List[str]) -> Dict:
        """
        Check if CLOs include sufficient higher-order thinking (analyze, evaluate, create).
        Returns validation report.
        """
        distribution = self.analyze_distribution(outcomes)
        hot_count = sum(distribution.get(level, 0) for level in ["analyze", "evaluate", "create"])
        total = len(outcomes)
        hot_ratio = hot_count / total if total > 0 else 0

        return {
            "distribution": distribution,
            "higher_order_count": hot_count,
            "total": total,
            "hot_ratio": round(hot_ratio, 2),
            "is_adequate": hot_ratio >= 0.3,  # At least 30% should be HOT
            "recommendation": (
                "Good distribution of higher-order thinking skills."
                if hot_ratio >= 0.3
                else "Consider adding more outcomes at Analyze, Evaluate, or Create levels."
            ),
        }


# Singleton
bloom_classifier = BloomClassifier()