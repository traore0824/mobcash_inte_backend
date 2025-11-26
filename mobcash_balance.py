import hashlib
import asyncio
import httpx
from datetime import datetime, timezone


def md5_hash(text: str) -> str:
    """Génère un hash MD5"""
    return hashlib.md5(text.encode()).hexdigest()


def sha256_hash(text: str) -> str:
    """Génère un hash SHA256"""
    return hashlib.sha256(text.encode()).hexdigest()


def create_confirm(cashdesk_id: int, hash_key: str) -> str:
    """Crée le paramètre 'confirm'"""
    data = f"{cashdesk_id}:{hash_key}"
    return md5_hash(data)


def create_headers(part1: str, part2: str) -> dict:
    """Crée les headers pour la requête"""
    sha_part1 = sha256_hash(part1)
    md5_part2 = md5_hash(part2)
    combined = sha256_hash(sha_part1 + md5_part2)
    return {"sign": combined}


async def get_balance(CASHDESK_ID, HASH_KEY, CASHIER_PASS):
    """Récupère le balance du cashdesk"""

    print("=" * 60)
    print("TEST DE LA FONCTION GET_BALANCE")
    print("=" * 60)

    # 1. Générer le timestamp
    dt = datetime.now(timezone.utc).strftime("%Y.%m.%d %H:%M:%S")
    print(f"\n1. Timestamp UTC: {dt}")

    # 2. Créer le confirm
    confirm = create_confirm(CASHDESK_ID, HASH_KEY)
    print(f"\n2. Confirm (MD5): {confirm}")

    # 3. Créer les parts pour le header
    part1 = f"hash={HASH_KEY}&cashierpass={CASHIER_PASS}&dt={dt}"
    part2 = f"dt={dt}&cashierpass={CASHIER_PASS}&cashdeskid={CASHDESK_ID}"

    print(f"\n3. Part1 (avant SHA256): {part1}")
    print(f"   Part2 (avant MD5): {part2}")

    # 4. Créer les headers
    headers = create_headers(part1, part2)
    print(f"\n4. Headers: {headers}")

    # 5. Construire l'URL et les params
    url = f"https://partners.servcul.com/CashdeskBotAPI/Cashdesk/{CASHDESK_ID}/Balance"
    params = {
        "confirm": confirm,
        "dt": dt
    }

    print(f"\n5. URL: {url}")
    print(f"   Params: {params}")

    # 6. Faire la requête
    print("\n6. Envoi de la requête...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)

            print(f"\n7. Status Code: {response.status_code}")
            print(f"   Response Headers: {dict(response.headers)}")

            # 8. Afficher la réponse
            print("\n8. RÉPONSE JSON:")
            print("=" * 60)

            result = response.json()

            # Affichage formaté
            if isinstance(result, dict):
                for key, value in result.items():
                    print(f"   {key}: {value}")
            else:
                print(result)

            print("=" * 60)

            # 9. Vérifier si le balance est présent
            if isinstance(result, dict) and "Balance" in result:
                print(f"\n✅ SUCCESS! Balance trouvé: {result['Balance']}")
            elif isinstance(result, dict) and "errorCode" in result:
                print(f"\n❌ ERREUR API: {result}")
            else:
                print(f"\n⚠️  Réponse inattendue: {result}")

            return result

    except httpx.TimeoutException:
        print("\n❌ ERREUR: Timeout de la requête")
        return None
    except httpx.RequestError as e:
        print(f"\n❌ ERREUR DE REQUÊTE: {e}")
        return None
    except Exception as e:
        print(f"\n❌ ERREUR INATTENDUE: {e}")
        return None