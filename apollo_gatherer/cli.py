"""Command line interface for gathering Apollo contacts."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Iterable, List, Sequence, Set

from .api import ApolloClient, ApolloError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Search Apollo.io for contacts matching job titles, company names, "
            "and a country, then export the results to CSV."
        )
    )

    parser.add_argument(
        "--job-title",
        dest="job_titles",
        action="append",
        default=[],
        help="Job title keyword. Provide multiple --job-title options for more than one keyword.",
    )
    parser.add_argument(
        "--job-titles",
        dest="job_titles_csv",
        help="Comma-separated list of job title keywords.",
    )
    parser.add_argument(
        "--company",
        dest="companies",
        action="append",
        default=[],
        help="Company name. Provide multiple --company options for more than one company.",
    )
    parser.add_argument(
        "--companies-file",
        dest="companies_file",
        help="Path to a text file containing company names (one per line).",
    )
    parser.add_argument(
        "--country",
        required=True,
        help="Country filter (for example: United States).",
    )
    parser.add_argument(
        "--output",
        default="apollo_contacts.csv",
        help="Destination CSV file. Defaults to './apollo_contacts.csv'.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=25,
        help="Number of contacts to request per page (Apollo allows up to 200).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of result pages to request.",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.5,
        help="Delay (in seconds) between page requests to respect rate limits.",
    )
    parser.add_argument(
        "--api-key",
        help="Apollo API key. If omitted, the script will read APOLLO_API_KEY from the environment.",
    )
    parser.add_argument(
        "--max-contacts",
        type=int,
        help="Maximum number of contacts to gather (stops once this limit is reached). Useful for testing and saving credits.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    job_titles = _collect_job_titles(args.job_titles, args.job_titles_csv)
    if not job_titles:
        parser.error("At least one job title keyword must be provided.")

    company_names = _collect_companies(args.companies, args.companies_file)
    if not company_names:
        parser.error("At least one company name must be provided (via --company or --companies-file).")

    # Try to get API key from: 1) command line, 2) environment variable, 3) local config file
    api_key = args.api_key or os.getenv("APOLLO_API_KEY")
    
    # Try loading from local config file if not found
    if not api_key:
        # Try multiple possible locations for config_local.py
        possible_paths = [
            Path.cwd() / "config_local.py",  # Current working directory
            Path(__file__).parent.parent / "config_local.py",  # Project root relative to this file
        ]
        for config_path in possible_paths:
            if config_path.exists():
                try:
                    # Read and exec the config file
                    config_globals = {}
                    with open(config_path, "r") as f:
                        exec(f.read(), config_globals)
                    api_key = config_globals.get("APOLLO_API_KEY")
                    if api_key:
                        break
                except Exception:
                    continue  # Try next path
    
    if not api_key:
        parser.error(
            "Apollo API key was not provided. Use --api-key, set APOLLO_API_KEY environment variable, "
            "or create a config_local.py file with APOLLO_API_KEY = 'your_key'"
        )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = ApolloClient(api_key=api_key)

    records = _gather_records(
        client,
        job_titles=job_titles,
        company_names=company_names,
        country=args.country,
        per_page=args.per_page,
        max_pages=args.max_pages,
        request_delay=args.request_delay,
        max_contacts=args.max_contacts,
    )

    _write_csv(output_path, records)
    return 0


def _collect_job_titles(cli_titles: Iterable[str], csv_titles: str | None) -> List[str]:
    titles: Set[str] = {title.strip() for title in cli_titles if title and title.strip()}
    if csv_titles:
        titles.update(part.strip() for part in csv_titles.split(",") if part.strip())
    return sorted(titles)


def _collect_companies(cli_companies: Iterable[str], companies_file: str | None) -> List[str]:
    companies: Set[str] = {company.strip() for company in cli_companies if company and company.strip()}
    if companies_file:
        for raw_line in Path(companies_file).expanduser().read_text().splitlines():
            value = raw_line.strip()
            if value:
                companies.add(value)
    return sorted(companies)


def _gather_records(
    client: ApolloClient,
    *,
    job_titles: Sequence[str],
    company_names: Sequence[str],
    country: str,
    per_page: int,
    max_pages: int | None,
    request_delay: float,
    max_contacts: int | None,
) -> List[dict]:
    seen_emails: Set[str] = set()
    results: List[dict] = []

    try:
        for person in client.search_people(
            job_titles=job_titles,
            company_names=company_names,
            country=country,
            per_page=per_page,
            max_pages=max_pages,
            request_delay=request_delay,
        ):
            email = person.get("email") or person.get("primary_email")
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)

            results.append(
                {
                    "name": _compose_name(person),
                    "role": person.get("title", ""),
                    "email": email,
                    "company": person.get("organization_name")
                    or person.get("organization", {}).get("name"),
                }
            )

            # Stop if we've reached the maximum number of contacts
            if max_contacts is not None and len(results) >= max_contacts:
                break
    except ApolloError as exc:
        raise SystemExit(f"Apollo API request failed: {exc}")

    return results


def _compose_name(person: dict) -> str:
    first = person.get("first_name", "").strip()
    last = person.get("last_name", "").strip()
    return (f"{first} {last}").strip()


def _write_csv(path: Path, records: Sequence[dict]) -> None:
    fieldnames = ["name", "role", "email", "company"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())


