"""Shared safety check for the scripts that edit a web map: this project only changes its own items."""
import sys


def own_item_or_exit(item, prefix: str, item_id: str, owner: str | None = None):
    """Stop unless the item exists, its title starts with this project's prefix, and (when known) the signed-in account owns it."""
    if item is None:
        sys.exit(f"Refused: no item with id {item_id} is visible to this account.")
    if not str(item.title).startswith(prefix):
        sys.exit(f"Refused: {item.title!r} ({item_id}) does not carry the {prefix!r} prefix. This project only changes its own items; "
                 "the Agentic_AI_City web maps are never edited from here.")
    if owner and getattr(item, "owner", owner) != owner:
        sys.exit(f"Refused: {item.title!r} ({item_id}) is owned by {item.owner}, not by {owner}.")
    return item
