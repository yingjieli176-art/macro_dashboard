"""Persist the latest official delayed VIX quote and confirmed daily close."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.vix_market import fetch_quote, write_quote, append_confirmed_close, SAVED_QUOTE


def main():
    quote = fetch_quote()
    write_quote(quote, SAVED_QUOTE)
    added = append_confirmed_close(quote)
    print("VIX", quote["value"], "quote time", quote["observed_at"], "confirmed close added", added)


if __name__ == "__main__":
    main()
