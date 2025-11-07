"""Apollo API client used to search for people and gather contact data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional

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
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "x-api-key": self.api_key,
            }
        )

    def search_people(
        self,
        *,
        job_titles: Optional[Iterable[str]] = None,
        company_names: Optional[Iterable[str]] = None,
        country: Optional[str] = None,
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

        payload_base: Dict[str, object] = {}

        titles = _to_list(job_titles)
        if titles:
            payload_base["person_titles"] = titles

        if country:
            payload_base["person_locations"] = [country]

        organizations = _to_list(company_names)
        if organizations:
            payload_base["organization_names"] = organizations

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

            response_json = self._request("POST", "/people/search", payload=payload)
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

    def iter_lists(
        self,
        *,
        per_page: int = 100,
        max_pages: Optional[int] = None,
        request_delay: float = 0.0,
    ) -> Iterator[Dict[str, object]]:
        page = 1
        while True:
            if max_pages is not None and page > max_pages:
                break

            params = {
                "api_key": self.api_key,
                "page": page,
                "per_page": per_page,
            }
            response_json = self._request("GET", "/lists", params=params)
            lists = response_json.get("lists") or response_json.get("results") or []
            if not lists:
                break

            for apollo_list in lists:
                yield apollo_list

            pagination = response_json.get("pagination", {})
            total_pages = pagination.get("total_pages")
            if total_pages is not None and page >= total_pages:
                break

            page += 1
            if request_delay:
                time.sleep(request_delay)

    def get_list_by_name(self, name: str) -> Optional[Dict[str, object]]:
        target = name.strip().lower()
        for apollo_list in self.iter_lists():
            list_name = (apollo_list.get("name") or "").strip().lower()
            if list_name == target:
                return apollo_list
        return None

    def iter_list_contacts(
        self,
        list_id: str,
        *,
        per_page: int = 50,
        max_contacts: Optional[int] = None,
        request_delay: float = 0.0,
    ) -> Iterator[Dict[str, object]]:
        page = 1
        yielded = 0

        while True:
            if max_contacts is not None and yielded >= max_contacts:
                break

            params = {
                "api_key": self.api_key,
                "page": page,
                "per_page": per_page,
            }

            response_json = self._request(
                "GET", f"/lists/{list_id}/contacts", params=params
            )
            contacts = (
                response_json.get("contacts")
                or response_json.get("list_contacts")
                or response_json.get("results")
                or []
            )
            if not contacts:
                break

            for contact in contacts:
                if max_contacts is not None and yielded >= max_contacts:
                    break
                yielded += 1
                yield contact

            pagination = response_json.get("pagination", {})
            total_pages = pagination.get("total_pages")
            if total_pages is not None and page >= total_pages:
                break

            page += 1
            if request_delay:
                time.sleep(request_delay)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, object]] = None,
        params: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        url = f"{self.base_url}{path}"
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self.session.request(
                    method,
                    url,
                    json=payload if payload is not None else None,
                    params=params,
                    timeout=60,
                )
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


def _to_list(values: Optional[Iterable[str]]) -> List[str]:
    if values is None:
        return []
    return [value for value in (value.strip() for value in values) if value]


