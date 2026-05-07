# Video Script

5-minute screen recording demonstrating the search engine tool. The script
below is finalised in Phase 5; this file currently records the time budget
and the bullet points each segment must cover.

## Time budget

| Time        | Segment              | Hard cap |
|-------------|----------------------|----------|
| 0:00 - 2:00 | Live demonstration   | 2:00     |
| 2:00 - 3:30 | Code walkthrough     | 1:30     |
| 3:30 - 4:00 | Tests and CI         | 0:30     |
| 4:00 - 4:30 | Git workflow         | 0:30     |
| 4:30 - 5:00 | GenAI reflection     | 0:30     |

## 0:00 - 2:00  Live demonstration

Run the four primary commands on camera, in order:

1. `build` - run live for two or three pages so the audience sees real
   fetches, the 6-second sleep between requests, and the running progress
   output. Then a single visible video cut (caption: "build continued --
   full crawl takes about 60 seconds") jumps to the build summary line.
2. `load` - confirm the index round-trips from disk; show metadata.
3. `print indifference` - single-word posting list with frequency and
   positions.
4. `find good friends` - multi-word AND with TF-IDF ranking.
5. One edge case: unknown word or empty query.
6. *(Optional, only if extensions shipped)* `find --explain good friends`
   to show the per-term TF-IDF arithmetic. Auxiliary demos must come
   after the four primary commands, never interleaved.

## 2:00 - 3:30  Code walkthrough

- `models.py`: schema (Document, Posting, SearchIndex).
- `indexer.py`: tokenisation, deliberately narrow extraction scope.
- `search.py`: AND intersection, TF-IDF, phrase scan over positions.
- Trade-offs to name out loud: list vs set for positions; JSON vs binary;
  sync vs async crawl; TF-IDF vs BM25.

## 3:30 - 4:00  Tests and CI

- `pytest --cov` locally with the coverage number on screen.
- Highlight the test that asserts the crawler called `clock.sleep(6)`
  the expected number of times -- this is the deterministic evidence
  backing the live `build` segment.
- GitHub Actions tab showing the matrix of green runs.
- One `pytest-benchmark` table.

## 4:00 - 4:30  Git workflow

- `git log --oneline --graph --all` showing feature branches merging
  into `main`.
- `git tag` listing v0.1 / v0.5 / v0.9 / v0.95 / v1.0.
- One release page screenshot.

## 4:30 - 5:00  GenAI reflection

Pick two concrete moments from development -- one where AI accelerated
the work, one where it misled or required correction -- and one sentence
on the broader implication for learning. Talking points are drafted
below as the development progresses.

### Talking points (filled in during Phase 5)

- *Episode 1 (helpful):* TBD.
- *Episode 2 (misled / corrected):* TBD.
- *One-line implication:* TBD.
