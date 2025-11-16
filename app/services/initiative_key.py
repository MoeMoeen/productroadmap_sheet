"""Generate unique initiative keys.

Simple sequential key generator: INIT-000001, INIT-000002, ...

Can be replaced later with a year-based format like INIT-2025-000123.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative  # type: ignore


def generate_initiative_key(db: Session) -> str:
	"""Generate a new unique initiative_key.

	Looks up the highest numeric sequence in existing keys and increments.
	Falls back to INIT-000001 if no records exist or parsing fails.
	"""
	last = (
		db.query(Initiative)
		.order_by(Initiative.id.desc())
		.first()
	)
	next_num = 1
	# Safely get existing key string
	if last and getattr(last, "initiative_key", None):
		# Expect format INIT-XXXXXX
		parts = last.initiative_key.split("-")
		if len(parts) == 2 and parts[0] == "INIT":
			try:
				next_num = int(parts[1]) + 1
			except ValueError:
				next_num = last.id + 1  # fallback using id
		else:
			next_num = last.id + 1
	return f"INIT-{next_num:06d}"

