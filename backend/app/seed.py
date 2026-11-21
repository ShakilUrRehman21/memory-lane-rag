"""Demo archives for three people. Run `python backend/app/seed.py` (or set SEED_DEMO=1, the default on first start).

Sign in with alex_chen / sophia_taylor / marcus_vance and password `password123`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.ingestion.service import ingest_text  # noqa: E402
from app.reasoning.analysis import refresh_analysis  # noqa: E402
from app.storage.repo import Users  # noqa: E402

PASSWORD = "password123"

ARCHIVES = {
    "user_alex": {
        "username": "alex_chen", "email": "alex@memorylane.app", "display_name": "Alex Chen", "color": "#8b9cff",
        "bio": "Systems engineer turned AI researcher. Archive 2019–2026.",
        "docs": [
            ("Resume 2019", "2019-01-10", ["career"],
             "Summary: Backend Systems Engineer.\nSkills: Java, C++, MySQL, Linux, Distributed Systems.\n"
             "Experience: Built low-latency storage engines for a payments company."),
            ("2019 Journal — Systems engineering & early AI doubts", "2019-04-10", ["journal"],
             "I am focused purely on high-performance Java and C++ distributed database kernels. "
             "I don't think AI is relevant to my career. The neural network claims seem overhyped and impractical "
             "for mission-critical software engineering. I love the craft of squeezing microseconds out of a hot path."),
            ("2019 Journal — Burnout winter", "2019-12-02", ["journal", "wellbeing"],
             "I feel exhausted and stuck after a year of on-call rotations. I decided to start running three mornings a "
             "week to clear my head. Sleep has been terrible and I am anxious about whether this job is my future."),
            ("2020 Journal — Running and remote work", "2020-06-21", ["journal", "health"],
             "Running has become my anchor; I finished my first half marathon in June 2020 and felt proud. "
             "Remote work gave me back two hours a day. I started reading about machine learning out of boredom, "
             "but I still think it is mostly hype."),
            ("2021 Journal — First Python & PyTorch experiments", "2021-08-15", ["journal", "learning"],
             "Over the past few months, I have started learning machine learning out of curiosity. "
             "I have been coding in Python and training transformers on weekends. "
             "My perspective is shifting; deep learning has far more real-world power than I gave it credit for in 2019."),
            ("2022 Journal — The leap", "2022-11-30", ["journal", "career"],
             "I accepted an offer to join a small applied AI team as an ML engineer. I feel nervous but excited. "
             "My goal is to ship one production model that real users rely on within a year."),
            ("2023 Journal — Full commitment to AI applications", "2023-05-20", ["journal", "career"],
             "I decided to build AI applications full time. "
             "I have moved away from Java completely and work exclusively in Python, TypeScript, and FastAPI building "
             "retrieval systems. I am grateful I took the risk."),
            ("2024 Journal — Learning to rest", "2024-02-11", ["journal", "wellbeing"],
             "Looking back, I realized that my best ideas arrive on long runs, not at my desk. I started meditating ten "
             "minutes every morning and I feel calm in a way I did not in 2019."),
            ("2025 Journal — Senior AI engineer at a foundation lab", "2025-06-01", ["journal", "career"],
             "My primary career goal is to work as a senior AI engineer building multi-agent architectures and "
             "longitudinal memory. Looking back at my 2019 self, my career trajectory has completely transformed."),
            ("2026 Journal — Research agenda", "2026-02-14", ["journal", "research"],
             "My new goal is to publish AI research papers at top machine learning conferences. "
             "I want to solve mechanistic interpretability and continuous temporal reasoning in foundation models. "
             "Engineering alone is not satisfying anymore."),
            ("Resume 2026", "2026-01-10", ["career"],
             "Summary: AI Research Engineer.\nSkills: Python, PyTorch, Transformers, LLMs, RAG, Mechanistic "
             "Interpretability, FastAPI.\nExperience: Led a multi-agent memory system used by 40k people."),
        ],
    },
    "user_sophia": {
        "username": "sophia_taylor", "email": "sophia@genomic-ai.org", "display_name": "Dr. Sophia Taylor",
        "color": "#5eead4", "bio": "Molecular biologist turned computational genomics lead. Archive 2020–2026.",
        "docs": [
            ("2020 Lab Notebook — Wet lab focus", "2020-05-18", ["lab"],
             "I believe wet lab pipetting and in-vitro assays are the only reliable way to understand protein folding. "
             "I don't trust computational predictions or machine learning for drug discovery. The algorithms produce "
             "hallucinations."),
            ("2021 Diary — Lockdown in the lab", "2021-02-03", ["diary"],
             "I feel lonely working night shifts in an empty lab. My sister calls every Sunday and it keeps me going. "
             "I want to finish my postdoc before the end of 2022."),
            ("2022 Lab Notebook — Testing AlphaFold", "2022-09-12", ["lab"],
             "I have started using AlphaFold and computational structural modeling in our lab daily. "
             "The accuracy of deep learning in predicting protein backbones has shocked me. I am now learning Python to "
             "automate genomic screening."),
            ("2024 Lab Notebook — Generative molecular design", "2024-03-30", ["lab"],
             "I have transitioned to generative diffusion models for molecular candidate generation. "
             "I no longer spend long hours in the physical wet lab; my primary role is now directing machine learning "
             "for drug discovery."),
            ("2026 Lab Notebook — AI biological institute", "2026-01-20", ["lab"],
             "My goal is to lead an autonomous AI-driven biological discovery platform. "
             "I completely reversed my 2020 skepticism. Computational biological intelligence is now the foundation "
             "of my life's work."),
        ],
    },
    "user_marcus": {
        "username": "marcus_vance", "email": "marcus@aiventures.io", "display_name": "Marcus Vance",
        "color": "#f0abfc", "bio": "B2B SaaS product manager turned AI venture founder. Archive 2018–2026.",
        "docs": [
            ("2018 Founder Journal — B2B SaaS dogma", "2018-06-10", ["founder"],
             "I believe standard B2B workflow SaaS is the only scalable business model. "
             "I don't think foundational AI or deep tech is investable for early stage founders. Focus purely on "
             "seat-based software."),
            ("2020 Founder Journal — Fundraising fatigue", "2020-10-14", ["founder"],
             "We closed a small seed round after forty investor meetings. I feel tired but proud of the team. "
             "My plan is to reach one million in annual revenue by the end of 2021."),
            ("2023 Founder Journal — The generative shift", "2023-11-05", ["founder"],
             "Traditional seat-based workflow software is dead. "
             "Outcome-based AI agents are replacing human workflows. I decided to pivot my entire company to building "
             "vertical AI workers."),
            ("2026 Founder Journal — Autonomous AI enterprises", "2026-03-01", ["founder"],
             "Our company operates entirely on autonomous multi-agent pipelines. "
             "My goal is to fund and build next-generation physical and cognitive AI ventures."),
        ],
    },
}


def seed(reset: bool = True) -> None:
    init_db()
    h, s = hash_password(PASSWORD)
    for uid, spec in ARCHIVES.items():
        if Users.get(uid):
            if not reset:
                continue
            Users.delete(uid)
        Users.create(spec["username"], spec["display_name"], spec["email"], h, s, spec["color"], spec["bio"],
                     user_id=uid)
        for title, date, tags, content in spec["docs"]:
            ingest_text(uid, content, title, date, tags, refresh=False)
        refresh_analysis(uid)
        print(f"  ✓ {spec['display_name']}: {len(spec['docs'])} documents")


if __name__ == "__main__":
    print("Seeding Memory Lane demo archives…")
    seed()
    print(f"Done. Sign in as alex_chen / sophia_taylor / marcus_vance with password '{PASSWORD}'.")
