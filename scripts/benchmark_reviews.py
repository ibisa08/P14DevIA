"""Banc d'essai du temps de génération des revues de presse selon la longueur de la discussion.

Usage local uniquement, depuis backend/ (la clé Anthropic vient de backend/.env) :

    uv run --env-file .env python ../scripts/benchmark_reviews.py --dry-run   # estimation, 0 appel
    uv run --env-file .env python ../scripts/benchmark_reviews.py             # mesures réelles

Ce script vit hors de backend/ : il n'entre donc pas dans l'image Docker (contexte de build
= backend/). Il n'appelle que l'agent de revue (sans tools) : aucun appel WorldNewsAPI, et il
n'importe pas `main` (donc pas de traçage MLflow ni de serveur).
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from agents.history import to_transcript  # noqa: E402
from agents.review_agent import REVIEW_INSTRUCTIONS, review_agent  # noqa: E402
from schemas import ChatMessageRead  # noqa: E402

DEFAULT_MODEL = "anthropic:claude-haiku-5-5"
# Tarifs Haiku 5.5 en dollars par million de tokens (prompts jusqu'à 100 000 tokens)
PRICE_INPUT_PER_M = 0.10
PRICE_OUTPUT_PER_M = 0.50
LENGTHS = [2, 6, 12, 20, 40]
TOPIC = "Le télétravail dans la fonction publique"
# Estimation grossière hors ligne pour le français : environ 3,5 caractères par token
CHARS_PER_TOKEN = 3.5
ESTIMATED_OUTPUT_TOKENS = 700
IMAGES_DIR = ROOT / "docs" / "images"
RESULTS_FILE = ROOT / "docs" / "benchmark_reviews.json"

# Longueurs mesurées sur les discussions de la base locale (8 discussions non vides, 9 messages
# du journaliste et 9 de l'assistant, contenu jamais affiché) : questions de 66 caractères en
# moyenne, réponses de 1 270 caractères en moyenne (médiane ~1 050, maximum ~3 350).
REAL_USER_CHARS = 66
REAL_ASSISTANT_CHARS = 1270

# Discussion synthétique sur un sujet unique. Médias et liens sont fictifs (domaines .example) :
# rien ici n'est une information réelle. Les phrases sont recombinées pour atteindre la
# longueur mesurée ; seul compte ici le volume de texte envoyé à l'agent de revue.
QUESTIONS = [
    "Où en est le télétravail dans la fonction publique ?",
    "Quelles différences entre les trois versants ?",
    "Que disent les syndicats ?",
    "Y a-t-il des études sur la productivité ?",
    "Et côté coûts pour l'administration ?",
    "Des exemples de collectivités qui ont tranché ?",
    "Qu'en pensent les usagers ?",
    "Le cadre juridique a-t-il changé récemment ?",
    "Quelles évolutions attendre l'an prochain ?",
    "Peux-tu résumer les points de désaccord ?",
    "Que font les autres pays européens ?",
    "Quel impact sur l'immobilier de l'État ?",
    "Comment les managers vivent-ils ce changement ?",
    "Des difficultés de cybersécurité signalées ?",
    "Et pour les agents en situation de handicap ?",
    "Quelle place pour la formation à distance ?",
    "Des chiffres sur l'absentéisme ?",
    "Comment se passent les recrutements ?",
    "Quelles critiques de l'opposition ?",
    "Peux-tu récapituler les sources citées ?",
]
FACTS = [
    "Selon l'enquête de Journal Exemple, un agent sur trois télétravaille au moins un jour par "
    "semaine dans la fonction publique d'État, avec un plafond de trois jours soumis à l'accord "
    "du chef de service.",
    "Radio Exemple relève un net écart entre versants : plus de 40 % des agents concernés pour "
    "l'État, autour de 20 % pour la territoriale et moins de 10 % pour l'hospitalière, faute de "
    "postes compatibles.",
    "Deux syndicats réclament une indemnité de télétravail revalorisée et un droit à la "
    "déconnexion inscrit dans les accords, quand un troisième redoute une inégalité entre "
    "agents télétravaillables et agents de terrain.",
    "Une enquête de l'Observatoire Exemple auprès de 2 400 agents indique que 68 % "
    "déclarent "
    "une productivité stable ou meilleure, mais que 41 % signalent des difficultés de "
    "collaboration.",
    "Les auteurs de l'étude insistent sur sa limite : elle repose sur des déclarations "
    "d'agents et non sur des mesures objectives de production, ce qui invite à relativiser "
    "les chiffres.",
    "La réduction des surfaces de bureaux pourrait économiser plusieurs dizaines de millions "
    "d'euros par an, mais l'équipement informatique et la sécurité des accès à distance "
    "absorbent une partie du gain.",
    "Une métropole a généralisé deux jours de télétravail avec des bureaux partagés, tandis "
    "qu'un département a restreint le dispositif après des retards dans le traitement de "
    "dossiers.",
    "Un sondage indique que 57 % des usagers ne remarquent aucun changement de qualité de "
    "service, alors que 22 % dénoncent des délais allongés pour joindre un agent.",
    "Un décret précise la prise en charge des frais et l'encadrement des horaires, sans "
    "créer de droit automatique au télétravail : les employeurs conservent la main sur "
    "l'organisation.",
    "Une concertation s'ouvre avec les employeurs publics sur un bilan chiffré et des règles de "
    "recours en cas de refus, mais son calendrier reste incertain.",
    "Plusieurs pays voisins ont inscrit un droit de demander le télétravail sans l'imposer, avec "
    "des modalités très variables d'un ministère à l'autre.",
    "Des managers disent manquer d'outils pour suivre l'activité à distance et réclament une "
    "formation dédiée, quand d'autres jugent que la confiance suffit.",
    "Les services informatiques signalent une hausse des tentatives d'hameçonnage visant les "
    "accès à distance, et recommandent une double authentification généralisée.",
    "Des associations rappellent que le télétravail peut faciliter le maintien dans l'emploi des "
    "personnes handicapées, à condition d'un équipement adapté financé par l'employeur.",
]
ANSWER_SCALE = [0.6, 1.4, 0.9, 1.1, 0.8, 1.2, 1.0, 0.7, 1.3, 1.0]  # moyenne 1,0


def make_answer(index: int) -> str:
    """Réponse de l'assistant d'environ REAL_ASSISTANT_CHARS caractères (± variation fixe)."""
    target = round(REAL_ASSISTANT_CHARS * ANSWER_SCALE[index % len(ANSWER_SCALE)])
    source = (
        f" Source : https://media-{index % 7}.example/societe/"
        f"teletravail-fonction-publique-dossier-{index}-analyse-detaillee"
    )
    parts: list[str] = []
    size = len(source)
    step = 0
    while size < target - 90:  # 90 : demi-phrase moyenne
        sentence = FACTS[(index * 3 + step) % len(FACTS)]
        parts.append(sentence)
        size += len(sentence) + 1
        step += 1
    return " ".join(parts) + source


EXCHANGES = [(QUESTIONS[i], make_answer(i)) for i in range(len(QUESTIONS))]


def build_messages(length: int) -> list[ChatMessageRead]:
    """Discussion de `length` messages (questions et réponses alternées, `length` pair)."""
    from datetime import UTC, datetime

    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    messages: list[ChatMessageRead] = []
    for question, answer in EXCHANGES[: length // 2]:
        messages.append(ChatMessageRead(role="user", content=question, created_at=now))
        messages.append(ChatMessageRead(role="assistant", content=answer, created_at=now))
    return messages


def build_prompt(length: int) -> str:
    # Même format que generate_review (backend/src/agents/review_agent.py)
    transcript = to_transcript(build_messages(length))
    return f"Sujet de la revue de presse : {TOPIC}\n\nHistorique de la discussion :\n\n{transcript}"


def cost(input_tokens: float, output_tokens: float) -> float:
    return input_tokens * PRICE_INPUT_PER_M / 1e6 + output_tokens * PRICE_OUTPUT_PER_M / 1e6


def estimate_input_tokens(length: int) -> int:
    chars = len(REVIEW_INSTRUCTIONS) + len(build_prompt(length))
    # + schéma de sortie envoyé comme outil : environ 300 tokens
    return round(chars / CHARS_PER_TOKEN) + 300


@dataclass
class Run:
    length: int
    seconds: float
    input_tokens: int
    output_tokens: int
    requests: int
    articles: int
    error: str | None = None


def print_estimate(repeats: int) -> float:
    print(f"Estimation hors ligne ({repeats} mesures par longueur + 1 appel d'échauffement)\n")
    print(f"{'messages':>9} {'tokens entrée':>14} {'tokens sortie':>14} {'coût/appel':>11}")
    total = cost(estimate_input_tokens(LENGTHS[0]), ESTIMATED_OUTPUT_TOKENS)  # échauffement
    for length in LENGTHS:
        tokens_in = estimate_input_tokens(length)
        per_call = cost(tokens_in, ESTIMATED_OUTPUT_TOKENS)
        total += per_call * repeats
        print(f"{length:>9} {tokens_in:>14} {ESTIMATED_OUTPUT_TOKENS:>14} {per_call:>10.5f}$")
    print(f"\nAppels : {len(LENGTHS) * repeats + 1}. Coût total estimé : {total:.4f} $")
    return total


async def measure(model: str, length: int) -> Run:
    start = time.perf_counter()
    try:
        result = await review_agent.run(build_prompt(length), model=model)
    except Exception as exc:  # noqa: BLE001 - on note l'échec et on continue le banc d'essai
        elapsed = time.perf_counter() - start
        return Run(length, elapsed, 0, 0, 0, 0, error=f"{type(exc).__name__}: {exc}"[:200])
    elapsed = time.perf_counter() - start
    usage = result.usage
    return Run(
        length,
        elapsed,
        usage.input_tokens,
        usage.output_tokens,
        usage.requests,
        len(result.output.articles),
    )


async def run_benchmark(model: str, repeats: int, max_cost: float) -> list[Run]:
    runs: list[Run] = []
    spent = 0.0
    failures = 0
    # Échauffement (connexion TLS, import paresseux du SDK), exclu des résultats
    warmup = await measure(model, LENGTHS[0])
    print(f"échauffement : {warmup.seconds:.1f} s {warmup.error or ''}")
    spent += cost(warmup.input_tokens, warmup.output_tokens)
    # Tours alternés entre les longueurs : une lenteur passagère de l'API ne pénalise pas
    # une seule longueur
    for repeat in range(repeats):
        for length in LENGTHS:
            run = await measure(model, length)
            runs.append(run)
            spent += cost(run.input_tokens, run.output_tokens)
            failures = failures + 1 if run.error else 0
            status = run.error or (
                f"{run.seconds:5.1f} s | {run.input_tokens} tok entrée | "
                f"{run.output_tokens} tok sortie | {run.articles} articles"
            )
            print(f"[{repeat + 1}/{repeats}] {length:>2} messages : {status}")
            if failures >= 3:
                sys.exit("Trois échecs de suite : arrêt pour ne pas dépenser inutilement.")
            if spent > max_cost:
                sys.exit(f"Coût {spent:.4f} $ au-delà du plafond {max_cost} $ : arrêt.")
    print(f"\nCoût calculé d'après les tokens mesurés : {spent:.5f} $")
    return runs


def summarize(runs: list[Run]) -> list[dict]:
    rows = []
    for length in LENGTHS:
        ok = [run for run in runs if run.length == length and not run.error]
        seconds = [run.seconds for run in ok]
        rows.append(
            {
                "messages": length,
                "n": len(ok),
                "mean": statistics.mean(seconds),
                "median": statistics.median(seconds),
                "stdev": statistics.stdev(seconds) if len(seconds) > 1 else 0.0,
                "min": min(seconds),
                "max": max(seconds),
                "input_tokens": statistics.mean(run.input_tokens for run in ok),
                "output_tokens": statistics.mean(run.output_tokens for run in ok),
            }
        )
    return rows


def print_table(rows: list[dict]) -> None:
    print("\n| Messages | n | Moyenne (s) | Médiane (s) | Écart-type (s) | Min (s) | Max (s) "
          "| Tokens entrée (moy.) | Tokens sortie (moy.) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(
            f"| {row['messages']} | {row['n']} | {row['mean']:.2f} | {row['median']:.2f} "
            f"| {row['stdev']:.2f} | {row['min']:.2f} | {row['max']:.2f} "
            f"| {row['input_tokens']:.0f} | {row['output_tokens']:.0f} |"
        )


def draw_chart(rows: list[dict], runs: list[Run], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = [row["messages"] for row in rows]
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    # Points individuels, puis moyenne avec étendue min-max
    for run in runs:
        if not run.error:
            ax.scatter(run.length, run.seconds, color="#8a8fa3", s=18, alpha=0.7, zorder=2)
    means = [row["mean"] for row in rows]
    lower = [row["mean"] - row["min"] for row in rows]
    upper = [row["max"] - row["mean"] for row in rows]
    ax.errorbar(x, means, yerr=[lower, upper], color="#5b21b6", marker="o", linewidth=2,
                capsize=5, label="Moyenne (barres : min – max)", zorder=3)
    ax.set_xticks(x)
    ax.set_xlabel("Nombre de messages dans la discussion")
    ax.set_ylabel("Temps de génération de la revue (s)")
    ax.set_title("Génération d'une revue de presse selon la longueur du chat (Haiku 5.5)")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.3)
    ax.scatter([], [], color="#8a8fa3", s=18, label="Mesures individuelles")
    ax.legend(loc="lower right")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repeats", type=int, default=5, help="mesures par longueur")
    parser.add_argument("--max-cost", type=float, default=0.05, help="plafond en dollars")
    parser.add_argument("--dry-run", action="store_true", help="estime le coût, sans appel")
    args = parser.parse_args()

    estimate = print_estimate(args.repeats)
    if args.dry_run:
        return
    if args.model == "test" or not args.model.startswith("anthropic:"):
        sys.exit("Ce banc d'essai mesure un vrai modèle Anthropic (anthropic:claude-haiku-5-5).")
    if estimate > args.max_cost:
        sys.exit(f"Estimation {estimate:.4f} $ au-delà du plafond {args.max_cost} $.")

    runs = asyncio.run(run_benchmark(args.model, args.repeats, args.max_cost))
    rows = summarize(runs)
    print_table(rows)
    RESULTS_FILE.write_text(
        json.dumps({"model": args.model, "runs": [asdict(r) for r in runs], "summary": rows},
                   indent=2, ensure_ascii=False)
    )
    draw_chart(rows, runs, IMAGES_DIR / "benchmark_reviews.png")
    print(f"\nRésultats : {RESULTS_FILE.relative_to(ROOT)}, "
          f"graphique : docs/images/benchmark_reviews.png")


if __name__ == "__main__":
    main()
