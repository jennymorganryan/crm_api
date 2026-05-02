import json
import os
import re
from collections import Counter
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def extract_json_object(raw_text):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            return {"findings": []}

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"findings": []}


def clean_score(value):
    try:
        score = float(value)
        return max(0, min(score, 1))
    except (TypeError, ValueError):
        return 0


def analyze_review_with_ai(review_text, item_name=None, star_rating=None):
    message = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=1200,
        temperature=0.2,
        system="""
You analyze furniture ecommerce reviews.

Return JSON only with this exact shape:
{
  "findings": [
    {
      "issue_category": "comfort | quality | delivery | assembly | color_accuracy | size | support | durability | value | positive_feedback | other",
      "target_text": "short product part or feature being discussed",
      "assessment_text": "short summary of what the customer said",
      "sentiment_label": "positive | neutral | negative",
      "positive_score": 0.0,
      "neutral_score": 0.0,
      "negative_score": 0.0,
      "key_phrases": "comma-separated phrases"
    }
  ]
}

Rules:
Return JSON only.
Extract real product feedback only.
Do not invent issues.
Scores must be decimals between 0 and 1.
Scores should roughly add up to 1.
If the review is mostly positive, include positive_feedback.
If there are no useful findings, return {"findings": []}.
""",
        messages=[
            {
                "role": "user",
                "content": json.dumps({
                    "item_name": item_name,
                    "star_rating": star_rating,
                    "review_text": review_text
                })
            }
        ]
    )

    raw_text = message.content[0].text
    parsed = extract_json_object(raw_text)
    findings = parsed.get("findings", [])

    cleaned_findings = []

    for finding in findings:
        cleaned_findings.append({
            "issue_category": finding.get("issue_category", "other"),
            "target_text": finding.get("target_text", ""),
            "assessment_text": finding.get("assessment_text", ""),
            "sentiment_label": finding.get("sentiment_label", "neutral"),
            "positive_score": clean_score(finding.get("positive_score")),
            "neutral_score": clean_score(finding.get("neutral_score")),
            "negative_score": clean_score(finding.get("negative_score")),
            "key_phrases": finding.get("key_phrases", "")
        })

    return cleaned_findings


def build_ai_recommendations(findings, total_reviews):
    grouped = {}

    for finding in findings:
        category = finding.get("issue_category", "other")

        if category == "positive_feedback":
            continue

        grouped.setdefault(category, []).append(finding)

    recommendations = []

    for category, items in grouped.items():
        mention_count = len(items)

        negative_mentions = sum(
            1 for item in items
            if item.get("sentiment_label") == "negative"
        )

        issue_rate = mention_count / max(total_reviews, 1)

        if issue_rate >= 0.40 or negative_mentions >= 3:
            priority = "high"
        elif issue_rate >= 0.20 or negative_mentions >= 2:
            priority = "medium"
        else:
            priority = "low"

        common_phrases = []

        for item in items:
            phrases = item.get("key_phrases", "")
            common_phrases.extend(
                [phrase.strip() for phrase in phrases.split(",") if phrase.strip()]
            )

        phrase_summary = ", ".join(
            phrase for phrase, count in Counter(common_phrases).most_common(5)
        )

        recommendations.append({
            "issue_category": category,
            "recommendation_title": f"Improve {category.replace('_', ' ')}",
            "recommendation_detail": (
                f"Customers mentioned issues related to {category.replace('_', ' ')}. "
                f"Review the product description, photos, supplier quality, customer expectations, and return data for this product area."
            ),
            "priority_level": priority,
            "evidence_summary": (
                f"{mention_count} out of {total_reviews} reviews mentioned this. "
                f"Common evidence: {phrase_summary or 'No repeated phrase pattern.'}"
            ),
            "review_count": total_reviews,
            "mention_count": mention_count
        })

    return recommendations