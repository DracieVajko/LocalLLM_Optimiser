"""Scoring version stamp.

Rows written before this version was introduced carry no ``scoring_version``
field and are treated as legacy (scoring_version = 0). Rows with different
versions must never be averaged together; scoreboards group by
``scoring_version`` and refuse to mix.

Bumped whenever the way a score is computed changes (see CHANGELOG).
"""

SCORING_VERSION = 7
