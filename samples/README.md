# samples/

Drop real KRX clearing-and-settlement log files here for manual testing
of the parser / Streamlit UI. Contents are **not** checked into git
(see `.gitignore`) — they may contain production-confidential data.

- Small, synthetic byte fixtures for the automated test suite live in
  `tests/fixtures/`, not here.
- Large real logs go here.
- The Streamlit Paste/Upload page can read from any path; the
  convention is `samples/<YYYYMMDD>/<TR_code>_*.log` to keep things
  tidy, but nothing enforces it.
