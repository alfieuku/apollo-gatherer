"""Apollo API client used to search for people and gather contact data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Union

import requests


class ApolloError(RuntimeError):
    """Raised when the Apollo API reports an error."""


@dataclass
class ApolloClient:
    """Thin wrapper around the Apollo REST API.

    Parameters
    ----------
    api_key:
        Apollo API key. Obtain this in the Apollo dashboard under Integrations.
    base_url:
        Base Apollo API URL. Defaults to the public v1 endpoint.
    max_retries:
        Maximum number of times to retry a request when Apollo responds with a
        rate-limit (HTTP 429) response.
    backoff_factor:
        Multiplier applied between retries. The sleep duration is calculated as
        ``backoff_factor * (2 ** (retry - 1))``.
    """

    api_key: str
    base_url: str = "https://api.apollo.io/api/v1"
    max_retries: int = 5
    backoff_factor: float = 1.5
    session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        })

    def search_people(
        self,
        *,
        job_titles: Iterable[str],
        company_names: Iterable[str],
        country: str,
        per_page: int = 25,
        max_pages: Optional[int] = None,
        request_delay: float = 0.0,
        extra_filters: Optional[Dict[str, object]] = None,
    ) -> Iterator[Dict[str, object]]:
        """Yield people that match the provided filters.

        Parameters
        ----------
        job_titles:
            Keywords that must appear in the contact's job title.
        company_names:
            List of company names to scope the search to.
        country:
            Country ("United States", "United Kingdom", etc.) used as a
            location filter.
        per_page:
            Apollo page size. Must be between 1 and 200 according to Apollo
            limits.
        max_pages:
            Optionally cap the number of pages that will be requested.
        request_delay:
            Number of seconds to sleep between page fetches to respect rate
            limits.
        extra_filters:
            Optional Apollo filter payload that will be merged into the request
            body, allowing advanced callers to refine the query.
        """

        payload_base: Dict[str, object] = {
            "person_titles": _to_list(job_titles),
            "person_locations": [country],
            "organization_names": _to_list(company_names),
        }

        if extra_filters:
            payload_base.update(extra_filters)

        page = 1
        while True:
            if max_pages is not None and page > max_pages:
                break

            payload = {
                **payload_base,
                "api_key": self.api_key,  # Apollo accepts api_key in body
                "page": page,
                "per_page": per_page,
            }

            # Also try x-api-key header (some Apollo endpoints prefer this)
            headers = {"x-api-key": self.api_key}
            response_json = self._post("/people/search", payload, headers=headers)
            people = response_json.get("people", [])
            if not people:
                break

            for person in people:
                yield person

            pagination = response_json.get("pagination", {})
            total_pages = pagination.get("total_pages")
            if total_pages is not None and page >= total_pages:
                break

            page += 1
            if request_delay:
                time.sleep(request_delay)

    def _post(self, path: str, payload: Dict[str, object], headers: Optional[Dict[str, str]] = None) -> Dict[str, object]:
        url = f"{self.base_url}{path}"
        attempt = 0

        while True:
            attempt += 1
            try:
                request_headers = {**self.session.headers}
                if headers:
                    request_headers.update(headers)
                response = self.session.post(url, json=payload, headers=request_headers, timeout=60)
            except requests.RequestException as exc:  # pragma: no cover - rare
                raise ApolloError(f"Failed to call Apollo API: {exc}") from exc

            if response.status_code == 429:
                if attempt > self.max_retries:
                    raise ApolloError(
                        "Apollo rate limit reached and maximum retries exceeded"
                    )

                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    delay = float(retry_after)
                else:
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text[:500]  # First 500 chars of response
                raise ApolloError(
                    f"Apollo API error {response.status_code}: {detail}"
                )

            return _safe_json(response)


def _safe_json(response: requests.Response) -> Dict[str, object]:
    try:
        return response.json()
    except ValueError:  # pragma: no cover - defensive
        # Show first 500 chars of response for debugging
        preview = response.text[:500] if response.text else "(empty response)"
        raise ApolloError(
            f"Apollo API returned a non-JSON response. "
            f"Status: {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type', 'unknown')}, "
            f"Preview: {preview}"
        )


def _to_list(values: Iterable[str]) -> List[str]:
    return [value for value in (value.strip() for value in values) if value]


