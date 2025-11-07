# Apollo Gatherer

Command line helper that queries the Apollo.io API for contacts filtered by job title keywords, a set of companies, and a country. The tool exports the results to a CSV file containing the name, role, email, and company for each contact returned by Apollo.

## Prerequisites

- Python 3.10+
- An Apollo.io plan with API access
- Apollo API key stored in the `APOLLO_API_KEY` environment variable (or passed via `--api-key`)

## Getting Your Apollo API Key

To obtain your Apollo API key:

1. **Log in to Apollo.io**: Navigate to [https://www.apollo.io/](https://www.apollo.io/) and sign in to your account.

2. **Access Settings**:
   - Click on your profile icon in the top-right corner
   - Select "Settings" from the dropdown menu

3. **Navigate to Integrations**:
   - In the Settings menu, click on the "Integrations" tab
   - Scroll through the list until you find "Apollo API"
   - Click on the "Connect" button next to it

4. **Create a New API Key**:
   - Click on the "API Keys" tab
   - Click the "Create new key" button
   - Enter a name and description for your API key
   - Select the specific API endpoints you want the key to access, or toggle "Set as master key" to grant access to all endpoints
   - Click "Create API key"

5. **Copy Your API Key**: After creation, Apollo will display the full API key. Click "Copy" to copy it to your clipboard.

6. **Set the API Key**:
   ```bash
   export APOLLO_API_KEY=your_api_key_here
   ```
   
   Or pass it directly when running the tool:
   ```bash
   python -m apollo_gatherer --api-key your_api_key_here ...
   ```

**Note**: Keep your API key secure and never commit it to version control. Treat it like a password.

## Installation

Install dependencies:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```
python -m apollo_gatherer \
  --job-title "Marketing Manager" \
  --job-titles "Demand Generation,Head of Growth" \
  --company "Acme Corp" \
  --companies-file ./companies.txt \
  --country "United States" \
  --max-contacts 50 \
  --output ./output/contacts.csv
```

**Export contacts from an Apollo list:**
```
python -m apollo_gatherer \
  --list-name "Career Fair" \
  --max-contacts 50 \
  --output ./output/career_fair.csv
```

**Testing with limited contacts (saves credits):**
```
python -m apollo_gatherer \
  --job-title "CEO" \
  --company "Google" \
  --country "United States" \
  --max-contacts 2 \
  --seen-emails-file .apollo_seen_emails.txt \
  --output test_contacts.csv
```

Key options:

- `--job-title`: repeatable; specifies a job title keyword. Use multiple times for several keywords.
- `--job-titles`: comma-separated list of job title keywords.
- `--company`: repeatable; specifies a target company name.
- `--companies-file`: path to a newline-delimited file with company names.
- `--country`: required country filter (example: `United States`).
- `--list-name`: export contacts from a saved Apollo list (job/company filters become optional when this is provided).
- `--max-contacts`: optional limit on the number of contacts to gather. Stops once this limit is reached. Useful for testing and saving credits.
- `--max-pages`: optional limit on the number of Apollo result pages to fetch.
- `--request-delay`: seconds to wait between API requests (default `0.5`).
- `--seen-emails-file`: path to a text file used to remember which emails you have already revealed (default `.apollo_seen_emails.txt`). Contacts whose emails already exist in this file are skipped, helping conserve credits across runs.
- `--api-key`: optional explicit API key. Defaults to the `APOLLO_API_KEY` environment variable.

The resulting CSV has the columns: `name`, `role`, `email`, `company`.

## Notes

- Apollo enforces API rate limits. Increase `--request-delay` or reduce `--per-page` if you encounter rate-limit errors.
- Not every contact returned by Apollo includes an email address. The tool skips contacts without emails and deduplicates by email.
- Previously revealed emails are tracked in the `.apollo_seen_emails.txt` file (configurable via `--seen-emails-file`). Existing emails in this file are skipped on subsequent runs to help conserve credits.
- You can pass custom filters by modifying the `extra_filters` argument when using `ApolloClient.search_people` directly from Python.


