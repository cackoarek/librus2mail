# Librus Scraping & Network Rules

## Librus Synergia Protocol & Flow
1. **Authentication Flow (`login()`)**:
   - Step 1: GET `OAUTH_URL` (`https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata`)
   - Step 2: POST `AUTH_URL` (`https://api.librus.pl/OAuth/Authorization?client_id=46`) with form data `action=login`, `login`, `pass`.
   - Step 3: GET `GRANT_URL` (`https://api.librus.pl/OAuth/Authorization/Grant?client_id=46`)
   - Session cookies are persisted on `requests.Session`.

2. **Requests Response Handling Gotcha**:
   - `requests.Response` has **no attribute `error`**.
   - **Incorrect**: `logger.error(f"{res.status_code} {res.error}")` -> raises `AttributeError: 'Response' object has no attribute 'error'`.
   - **Correct**: Use `res.reason`, `res.text`, or `res.raise_for_status()`.

3. **Rate Limiting and Delays**:
   - Preserve `sleep(5)` delays between page fetches. Librus Synergia will block IPs or trigger CAPTCHAs if requests are sent in rapid bursts.

4. **Message Read Side Effect**:
   - Note: both `read_messages` and `read_grades` default to `true`. Users can set `read_messages: false` if they prefer not to mark messages as read on the web portal.

5. **HTML Parsing Resilience**:
   - Librus DOM is subject to change. Always guard BeautifulSoup queries against `None` before chaining methods:
     ```python
     table = soup.find('table', attrs={'class': 'decorated stretch'})
     if not table:
         logger.warning("Nie znaleziono tabeli wiadomości w odpowiedzi HTML")
         return []
     ```
   - Deduplication ID logic:
     - Messages: `tds[3].get_text().strip() + tds[4].get_text().strip() + tds[2].get_text()`
     - Notifications: `tds[0].get_text().strip() + tds[1].get_text().strip() + tds[2].get_text().strip()`

6. **State & Known Items Tracking**:
   - `__known_messages` and `__known_notifications` prevent re-sending identical items.
   - `do_not_send_first_parse` (`dry-parse`): On initial launch, existing messages are indexed into `known` without firing email notifications.
