"""End-to-end demo driver for Provenance Guard.

Exercises the full application through Flask's test client and writes structured
evidence to ``docs/demo_evidence.json``. Uses live Groq analysis when
``GROQ_API_KEY`` is set; otherwise the Groq signal reports ``available: false``
and the two local signals carry the ensemble (the numbers printed are still
real, never fabricated).

Usage:
    python scripts/run_demo.py --reset
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from provenance_guard import create_app
from provenance_guard.config import Config

AI_LIKE = (
    "It is important to note that artificial intelligence plays a crucial role "
    "in modern society. Furthermore, this multifaceted technology continues to "
    "evolve rapidly. Moreover, it is essential to delve into the various ways "
    "in which these systems foster innovation. In conclusion, the realm of "
    "artificial intelligence underscores the importance of careful, balanced, "
    "and thoughtful consideration across a wide range of domains and industries."
)

HUMAN_LIKE = (
    "My grandmother kept bees behind the shed, and every August the whole yard "
    "smelled of smoke and clover. She never wore the gloves. I asked her once "
    "if she was scared and she just laughed, said the bees knew her hands. When "
    "she died we found forty jars of honey in the cellar, dusty, still golden, "
    "each one labeled in her crooked little script with a year and nothing else."
)

BORDERLINE = (
    "The report outlines several findings. Data collection occurred over three "
    "months. Participants were selected at random from a large pool. Results "
    "suggest a modest correlation, though further study is warranted before any "
    "firm conclusions can be drawn about the underlying mechanisms involved."
)

IMAGE_META = {
    "filename": "artwork.png",
    "mime_type": "image/png",
    "width": 1024,
    "height": 1024,
    "software": "Midjourney",
    "has_exif": False,
    "edit_count": 0,
    "source_hash": "",
    "creator_attestation": False,
    "alt_text": "A surreal city floating above the clouds.",
}

CERT_RESPONSE_FILLER = (
    "I wrote this piece from my own memory over several evenings, revising the "
    "opening a few times and reading it aloud to catch the rhythm. I kept my "
    "outline and every intermediate draft in a folder and I am glad to walk "
    "anyone through the messy middle of the process because it was entirely my "
    "own work from the first sentence to the very last line submitted here."
)


def _signal_summary(signals: dict) -> dict:
    return {name: sig.get("score") for name, sig in signals.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Provenance Guard demo")
    parser.add_argument(
        "--reset", action="store_true", help="reset the demo database first"
    )
    args = parser.parse_args()

    load_dotenv()
    config = Config()
    if args.reset and os.path.exists(config.database_path):
        os.remove(config.database_path)
        print(f"[reset] removed {config.database_path}")

    app = create_app(config=config)  # real Groq signal (uses key if present)
    client = app.test_client()

    evidence: dict = {"groq_configured": config.groq_configured, "submissions": {}}
    print(f"Groq configured: {config.groq_configured}\n")

    # 1-5: three text submissions with full signal breakdown.
    for name, text in (("ai_like", AI_LIKE), ("human_like", HUMAN_LIKE),
                        ("borderline", BORDERLINE)):
        resp = client.post("/submit", json={"creator_id": "demo-creator", "text": text})
        data = resp.get_json()
        evidence["submissions"][name] = data
        print(f"=== {name} ===")
        print(f"  attribution : {data['attribution']}")
        print(f"  ai_likelihood: {data['ai_likelihood']}  confidence: {data['confidence']}")
        print(f"  signals     : {_signal_summary(data['signals'])}")
        print(f"  disagreement: {data['signal_disagreement']}")
        print(f"  label       : {data['transparency_label']['text']}\n")

    # 6-7: appeal the borderline submission and show under_review.
    appeal_target = evidence["submissions"]["borderline"]["content_id"]
    appeal_resp = client.post(
        "/appeal",
        json={
            "content_id": appeal_target,
            "creator_id": "demo-creator",
            "creator_reasoning": (
                "I wrote this summary myself from my own research notes and can "
                "provide the earlier drafts on request."
            ),
        },
    )
    evidence["appeal"] = appeal_resp.get_json()
    lookup = client.get(f"/content/{appeal_target}").get_json()
    print(f"Appeal status: {lookup['status']} (was {evidence['submissions']['borderline']['attribution']})\n")

    # 8: image-metadata submission.
    img_resp = client.post(
        "/submit/image-metadata",
        json={"creator_id": "demo-creator", "metadata": IMAGE_META},
    )
    evidence["image_metadata"] = img_resp.get_json()
    print("=== image_metadata ===")
    print(f"  attribution : {evidence['image_metadata']['attribution']}")
    print(f"  signals     : {_signal_summary(evidence['image_metadata']['signals'])}\n")

    # 9: certificate challenge + verify for the human-like (eligible) submission.
    cert_target = evidence["submissions"]["human_like"]["content_id"]
    ch = client.post(
        "/certificate/challenge",
        json={"content_id": cert_target, "creator_id": "demo-creator"},
    ).get_json()
    verify = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": cert_target,
            "creator_id": "demo-creator",
            "challenge_response": f"{ch['phrase']} {CERT_RESPONSE_FILLER}",
            "creator_attestation": True,
            "draft_evidence": ["draft-v1-notes.txt", "draft-v2-outline.txt"],
        },
    ).get_json()
    evidence["certificate"] = {"challenge": ch, "verification": verify}
    print(f"Certificate issued: {verify.get('certificate_id')} status={verify.get('status')}\n")

    # 10-11: analytics + audit log.
    evidence["analytics"] = client.get("/analytics").get_json()
    evidence["audit_log"] = client.get("/log?limit=50").get_json()
    print("Analytics:", json.dumps(evidence["analytics"], indent=2))
    print(f"\nAudit events captured: {evidence['audit_log']['count']}")

    # 12: persist structured evidence.
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "demo_evidence.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2)
    print(f"\nWrote evidence to {os.path.relpath(out_path)}")


if __name__ == "__main__":
    main()
