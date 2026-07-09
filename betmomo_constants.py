"""
Constantes BetMomo pour les tests.
"""

import os

from dotenv import load_dotenv

load_dotenv()

BETMOMO_TOKEN = os.getenv("BETMOMO_TOKEN", "")
BETMOMO_PLAYER_ID = os.getenv("BETMOMO_PLAYER_ID", "108464223")
BETMOMO_TEST_AMOUNT = int(os.getenv("BETMOMO_TEST_AMOUNT", "500"))
BETMOMO_TEST_PIN = os.getenv("BETMOMO_TEST_PIN", "")
BETMOMO_DRY_RUN = os.getenv("BETMOMO_DRY_RUN", "true").lower() in ("1", "true", "yes")
