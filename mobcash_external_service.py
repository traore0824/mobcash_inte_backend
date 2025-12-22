# external_integrations/services/mobcash_external_service.py

import requests
import logging
import hmac
import hashlib
import time
import json
from decimal import Decimal
from typing import Dict, Any, Optional
from django.conf import settings
import os 
from dotenv import load_dotenv

from accounts.models import AppName
from mobcash_inte.models import Transaction
connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")
load_dotenv()
logger = logging.getLogger('betting_transactions')


class MobCashExternalService:
    """
    Service de communication avec le backend MobCash API

    Authentification: API Key + HMAC Signature

    Endpoints disponibles:
    - Créer dépôt (deposit)
    - Créer retrait (withdrawal)
    - Vérifier joueur (verify_player)
    - Détails transaction par UUID
    - Détails transaction par external_id
    - Lister transactions
    - Demander annulation
    - Voir demande d'annulation
    - Lister toutes les demandes d'annulation user
    """

    def __init__(self):
        """
        Initialise le service avec la configuration active

        Raises:
            ValueError: Si aucune configuration active n'est trouvée
        """
        self.base_url = os.getenv("MOBCASHAPI_BASE_URL")
        self.api_key = os.getenv("MOBCASHAPI_API_KEY")
        self.api_secret = os.getenv("MOBCASHAPI_API_SECRET")
        self.timeout = 300

        logger.info(
            "[MOBCASH] [INIT] Service initialisé",
            extra={
                'base_url': self.base_url,
                'api_key': self.api_key[:10] + '...',  # Log seulement le début
                'timeout': self.timeout
            }
        )

    def _generate_signature(self, method: str, path: str, body: str, timestamp: int) -> str:
        """
        Génère la signature HMAC-SHA256 pour authentification

        Format: HMAC-SHA256(timestamp + method + path + body, api_secret)

        Args:
            method: Méthode HTTP (GET, POST, etc.)
            path: Chemin de l'endpoint (/api/v1/transactions/deposit/)
            body: Corps de la requête (JSON string normalisé, vide pour GET)
            timestamp: Unix timestamp

        Returns:
            Signature hexadécimale
        """
        message = f"{timestamp}{method}{path}{body}"

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        print(f"signaturesignature1111111 {signature}")

        logger.debug(
            "[MOBCASH] [SIGNATURE] Signature générée",
            extra={
                'method': method,
                'path': path,
                'timestamp': timestamp,
                'message_length': len(message),
                'body_length': len(body)
            }
        )

        return signature

    def _normalize_json_body(self, data: Dict) -> str:
        """
        Normalise le body JSON pour garantir une signature cohérente

        CRITIQUE: Le format doit être identique côté client et serveur
        - Pas d'espaces après les séparateurs
        - Clés triées alphabétiquement

        Args:
            data: Dictionnaire Python à sérialiser

        Returns:
            String JSON normalisé
        """
        return json.dumps(data, separators=(',', ':'), sort_keys=True)

    def _get_headers(self, method: str, path: str, body: str = '') -> Dict[str, str]:
        """
        Génère les headers d'authentification pour MobCash API

        Headers:
        - X-API-Key: API key
        - X-Timestamp: Unix timestamp
        - X-Signature: HMAC-SHA256 signature
        - Content-Type: application/json

        Args:
            method: Méthode HTTP
            path: Chemin endpoint
            body: Corps JSON normalisé (vide pour GET)

        Returns:
            Dict des headers
        """
        timestamp = int(time.time())
        signature = self._generate_signature(method, path, body, timestamp)

        return {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'X-Timestamp': str(timestamp),
            'X-Signature': signature
        }

    def _make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict] = None,
            params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Effectue une requête HTTP vers MobCash API

        Gestion complète des erreurs et logging détaillé

        Args:
            method: GET ou POST
            endpoint: Chemin relatif (/api/v1/transactions/deposit/)
            data: Données JSON (pour POST)
            params: Paramètres query string (pour GET)

        Returns:
            Dict avec 'success', 'data', 'error', etc.
        """
        url = f"{self.base_url}{endpoint}"
        body = ''

        # 🔥 NORMALISATION CRITIQUE DU BODY JSON
        if data and method == 'POST':
            body = self._normalize_json_body(data)

        headers = self._get_headers(method, endpoint, body)

        logger.info(
            f"[MOBCASH] [REQUEST_START] {method} {endpoint}",
            extra={
                'url': url,
                'has_data': bool(data),
                'has_params': bool(params),
                'body_length': len(body)
            }
        )

        try:
            if method == 'GET':
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
            elif method == 'POST':
                # 🔥 IMPORTANT: Envoyer le body normalisé en tant que string, pas json=data
                response = requests.post(
                    url,
                    data=body,  # Utiliser 'data' au lieu de 'json' pour garder le format exact
                    headers=headers,
                    timeout=self.timeout
                )
            else:
                raise ValueError(f"Méthode HTTP non supportée: {method}")

            logger.info(
                f"[MOBCASH] [RESPONSE] Status {response.status_code}",
                extra={
                    'status_code': response.status_code,
                    'content_type': response.headers.get('Content-Type'),
                    'response_length': len(response.text)
                }
            )

            # Parser réponse
            if response.status_code in (200, 201):
                try:
                    result = response.json()
                    logger.info(f"[MOBCASH] [SUCCESS] Requête réussie")
                    logger.debug(f"[MOBCASH] [RESPONSE_DATA] {result}")

                    return {
                        'success': True,
                        'data': result,
                        'status_code': response.status_code
                    }

                except ValueError as e:
                    error_msg = "Réponse invalide (JSON parsing error)"
                    logger.error(
                        f"[MOBCASH] [JSON_ERROR] {error_msg}",
                        extra={
                            'error': str(e),
                            'response_preview': response.text[:300]
                        }
                    )
                    return {
                        'success': False,
                        'error': error_msg,
                        'error_type': 'invalid_json',
                        'raw_response': response.text[:500]
                    }

            else:
                # Erreur HTTP
                error_msg = f"HTTP {response.status_code}"

                try:
                    error_detail = response.json()
                    if isinstance(error_detail, dict):
                        error_msg = error_detail.get('message') or error_detail.get('detail') or error_detail.get(
                            'error') or error_msg
                        error_code = error_detail.get('error_code') or error_detail.get('code')
                except:
                    pass

                logger.error(
                    f"[MOBCASH] [HTTP_ERROR] {error_msg}",
                    extra={
                        'status_code': response.status_code,
                        'response_preview': response.text[:300]
                    }
                )

                return {
                    'success': False,
                    'error': error_msg,
                    'error_type': 'http_error',
                    'status_code': response.status_code,
                    'raw_response': response.text[:500]
                }

        except requests.exceptions.Timeout:
            error_msg = f"Timeout après {self.timeout}s"
            logger.error(
                "[MOBCASH] [TIMEOUT]",
                extra={'timeout': self.timeout, 'url': url}
            )
            return {
                'success': False,
                'error': error_msg,
                'error_type': 'timeout'
            }

        except requests.exceptions.ConnectionError as e:
            error_msg = "Erreur de connexion au serveur MobCash"
            logger.error(
                "[MOBCASH] [CONNECTION_ERROR]",
                extra={'error': str(e), 'url': url}
            )
            return {
                'success': False,
                'error': error_msg,
                'error_type': 'connection_error'
            }

        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            logger.exception(
                "[MOBCASH] [UNEXPECTED_ERROR]",
                extra={'error': str(e), 'url': url}
            )
            return {
                'success': False,
                'error': error_msg,
                'error_type': 'unexpected_error'
            }

    # ========================================================================
    # CRÉER DÉPÔT
    # ========================================================================

    def create_deposit(
        self, transaction: Transaction 
    ) -> Dict[str, Any]:
        """
        Créer une transaction de dépôt

        POST /api/v1/transactions/deposit/

        Args:
            platform_uid: UUID de la plateforme (ex: betting platform)
            player_user_id: ID du joueur sur la plateforme externe
            amount: Montant du dépôt
            external_transaction_id: ID unique de la transaction côté plateforme
            payment_method: WAVE, MTN, MOOV, etc.
            phone_number: Numéro de téléphone (optionnel)
            metadata: Données supplémentaires (optionnel)

        Returns:
            Dict avec 'success', 'data' contenant la Transaction créée
        """
        endpoint = "/api/v1/transactions/deposit/"
        # platform_uid = transaction.app or AppName.objects.filter(name=transaction.plateforme).first()
        payload = {
            "platform_uid": self.get_plateform_id(transaction.app.name),
            "player_user_id": str(transaction.user_app_id),
            "amount": str(transaction.amount),
            "external_transaction_id": str(transaction.reference),
            "external_id": str(transaction.reference),
            "payment_method": str(transaction.network.name).upper(),
        }

        result = self._make_request("POST", endpoint, data=payload)

        if result.get("success"):
            data = result.get("data", {})
            mobcash_response = data.get("mobcash_response", {})
            raw_response = mobcash_response.get("raw_response", {})

            logger.info(
                "[MOBCASH] [DEPOSIT_SUCCESS] Dépôt réussi",
                extra={
                    "operation_id": raw_response.get("OperationId"),
                    "summa": raw_response.get("Summa"),
                },
            )

            return {
                "Summa": raw_response.get("Summa"),
                "OperationId": raw_response.get("OperationId"),
                "Success": raw_response.get("Success"),
                "Message": raw_response.get("Message"),
            }

        # ❌ Si success = False → retourne tout le body
        else:
            logger.error(
                "[MOBCASH] [DEPOSIT_FAILED] Échec création dépôt",
                extra={"error": result},
            )
            return result

    def create_withdrawal(
        self, transaction: Transaction 
    ) -> Dict[str, Any]:
        """
        Créer une transaction de retrait

        POST /api/v1/transactions/withdrawal/

        Args:
            platform_uid: UUID de la plateforme
            player_user_id: ID du joueur
            amount: Montant du retrait
            external_transaction_id: ID unique côté plateforme
            mobcash_code: code de retrait.
            phone_number: Numéro pour recevoir l'argent (REQUIS)
            metadata: Données supplémentaires

        Returns:
            Dict avec 'success', 'data' contenant la Transaction créée
        """
        endpoint = '/api/v1/transactions/withdraw/'
        # platform_uid = transaction.app or AppName.objects.filter(name=transaction.plateforme).first()
        payload = {
            "platform_uid": self.get_plateform_id(transaction.app.name),
            "player_user_id": str(transaction.user_app_id),
            "external_transaction_id": str(transaction.id),
            "external_id": str(transaction.reference),
            "mobcash_code": transaction.withdriwal_code,
        }

        result = self._make_request('POST', endpoint, data=payload)
        logger.info(f"[MOBCASH] [WITHDRAWAL_SUCCESS] result: {result}")
        if result.get("success"):
            data = result.get("data", {})
            mobcash_response = data.get("mobcash_response", {})
            raw_response = mobcash_response.get("raw_response", {})

            logger.info(
                "[MOBCASH] [DEPOSIT_SUCCESS] Dépôt réussi",
                extra={
                    "operation_id": raw_response.get("OperationId"),
                    "summa": raw_response.get("Summa"),
                },
            )

            return {
                "Summa": raw_response.get("Summa"),
                "OperationId": raw_response.get("OperationId"),
                "Success": raw_response.get("Success"),
                "Message": raw_response.get("Message"),
            }

        # ❌ Si success = False → retourne tout le body
        else:
            logger.error(
                "[MOBCASH] [DEPOSIT_FAILED] Échec création dépôt",
                extra={"error": result},
            )
            return result

    # ========================================================================
    # VÉRIFIER JOUEUR
    # ========================================================================

    def verify_player(self, code: str, player_user_id: str) -> Dict[str, Any]:
        """
        Vérifier l'existence d'un joueur sur une plateforme

        Retourne uniquement les informations du joueur sous le format :
        {
            "UserId": int,
            "Name": str,
            "CurrencyId": int
        }
        """
        endpoint = '/api/v1/transactions/verify-player/'

        payload = {
            "platform_uid": str(self.get_plateform_id(code)),
            "player_user_id": str(player_user_id),
        }

        logger.info(
            "[MOBCASH] [VERIFY_PLAYER_START] Vérification joueur",
            
        )

        result = self._make_request('POST', endpoint, data=payload)
        connect_pro_logger.info(f"result result {result}")

        if result.get('success') and 'data' in result:

            data = result['data']
            player = data.get('player', {})

            # logger.info(
            #     "[MOBCASH] [VERIFY_PLAYER_SUCCESS] Joueur vérifié",
            #     extra={'player_user_id': player.get('user_id')}
            # )
            # ✅ Retourne seulement ce que tu veux, avec les clés renommées
            return {
                "UserId": player.get('user_id'),
                "Name": player.get('name'),
                "CurrencyId": player.get('currency_id')
            }

        else:
            logger.error(
                "[MOBCASH] [VERIFY_PLAYER_FAILED] Échec vérification",
                extra={'error': result.get('error')}
            )
            return {}

    # ========================================================================
    # DÉTAILS TRANSACTION PAR UUID
    # ========================================================================

    def get_transaction_by_uuid(self, transaction_uuid: str) -> Dict[str, Any]:
        """
        Récupérer les détails d'une transaction par son UUID

        GET /api/v1/transactions/list/{uuid}/

        Args:
            transaction_uuid: UUID de la transaction

        Returns:
            Dict avec 'success', 'data' contenant la Transaction complète
        """
        endpoint = f'/api/v1/transactions/list/{transaction_uuid}/'

        logger.info(
            "[MOBCASH] [GET_BY_UUID_START] Récupération transaction",
            extra={'transaction_uuid': transaction_uuid}
        )

        result = self._make_request('GET', endpoint)

        if result['success']:
            data = result['data']
            logger.info(
                "[MOBCASH] [GET_BY_UUID_SUCCESS] Transaction récupérée",
                extra={
                    'status': data.get('status'),
                    'amount': data.get('amount'),
                    'type': data.get('transaction_type')
                }
            )
        else:
            logger.error(
                "[MOBCASH] [GET_BY_UUID_FAILED] Transaction introuvable",
                extra={'error': result.get('error')}
            )

        return result

    from typing import Dict, Any, Optional
    def get_plateform_id(self, code: str) -> Optional[str]:
        """
        Récupère l'ID d'une plateforme à partir de son code (insensible à la casse).

        Exemple API : GET /api/v1/platforms/
        Réponse : { "results": [ { "id": "...", "code": "1xbet" }, ... ] }

        Args:
            code (str): code de la plateforme à rechercher (ex: "1XBET" ou "melbet")

        Returns:
            str | None: L'UUID de la plateforme si trouvée, sinon None
        """
        endpoint = "/api/v1/platforms/"
        result = self._make_request("GET", endpoint).get("data")
        connect_pro_logger.info(f"resultat de verification de user {result} et le code {code}")

        if not result or "results" not in result:
            return None

        # Normalise le code recherché (minuscule pour comparaison)
        search_code = code.strip().lower()

        for platform in result["results"]:
            # Compare insensible à la casse
            if platform.get("code", "").strip().lower() == search_code:
                connect_pro_logger.info(
                    f"resultat de verification de user iididid {platform.get('id')}"
                )
                return platform.get("id")

        # Si rien trouvé
        return None

    # ========================================================================
    # DÉTAILS TRANSACTION PAR EXTERNAL_ID
    # ========================================================================

    def get_transaction_by_external_id(
            self,
            platform_uid: str,
            external_transaction_id: str
    ) -> Dict[str, Any]:
        """
        Récupérer une transaction par son external_transaction_id

        GET /api/v1/transactions/by-external-id/

        Args:
            platform_uid: UUID de la plateforme
            external_transaction_id: ID externe de la transaction

        Returns:
            Dict avec 'success', 'data' contenant la Transaction
        """
        endpoint = f'api/v1/transactions/list/external/{str(external_transaction_id)}'

        params = {
            'platform_uid': str(platform_uid),
            'external_transaction_id': str(external_transaction_id)
        }

        logger.info(
            "[MOBCASH] [GET_BY_EXTERNAL_ID_START] Recherche transaction",
            extra={
                'platform_uid': platform_uid,
                'external_transaction_id': external_transaction_id
            }
        )

        result = self._make_request('GET', endpoint)

        if result['success']:
            data = result['data']
            logger.info(
                "[MOBCASH] [GET_BY_EXTERNAL_ID_SUCCESS] Transaction trouvée",
                extra={
                    'transaction_uuid': data.get('uuid'),
                    'status': data.get('status')
                }
            )
        else:
            logger.error(
                "[MOBCASH] [GET_BY_EXTERNAL_ID_FAILED] Transaction introuvable",
                extra={'error': result.get('error')}
            )

        return result

    # ========================================================================
    # LISTER TRANSACTIONS
    # ========================================================================

    def list_transactions(
            self,
            page: int = 1,
            page_size: int = 20,
            filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Lister les transactions avec pagination et filtres

        GET /api/v1/transactions/list/

        Args:
            page: Numéro de page
            page_size: Nombre d'éléments par page
            filters: Filtres optionnels:
                - status: PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED
                - transaction_type: DEPOSIT, WITHDRAWAL
                - payment_method: WAVE, MTN, MOOV, etc.
                - player_user_id: Filtrer par joueur
                - start_date: Date de début (YYYY-MM-DD)
                - end_date: Date de fin (YYYY-MM-DD)

        Returns:
            Dict avec 'success', 'data' contenant:
            {
                'count': int,
                'total_pages': int,
                'current_page': int,
                'page_size': int,
                'next': bool,
                'previous': bool,
                'results': [...]
            }
        """
        endpoint = '/api/v1/transactions/list/'

        params = {
            'page': page,
            'page_size': page_size
        }

        if filters:
            params.update(filters)

        logger.info(
            "[MOBCASH] [LIST_TRANSACTIONS_START] Récupération liste",
            extra={'page': page, 'page_size': page_size, 'filters': filters}
        )

        result = self._make_request('GET', endpoint, params=params)

        if result['success']:
            data = result['data']
            logger.info(
                "[MOBCASH] [LIST_TRANSACTIONS_SUCCESS] Liste récupérée",
                extra={
                    'count': data.get('count'),
                    'results_count': len(data.get('results', []))
                }
            )

        return result

    # ========================================================================
    # DEMANDER ANNULATION
    # ========================================================================

    def request_cancellation(self, transaction_uuid: str, reason: str) -> Dict[str, Any]:
        """
        Demander l'annulation d'une transaction

        POST /api/v1/transactions/list/{uuid}/request-cancellation/

        Args:
            transaction_uuid: UUID de la transaction
            reason: Raison de l'annulation

        Returns:
            Dict avec 'success', 'data' contenant CancellationRequest créé
        """
        endpoint = f'/api/v1/transactions/list/{transaction_uuid}/request-cancellation/'

        payload = {
            'reason': str(reason)
        }

        logger.info(
            "[MOBCASH] [REQUEST_CANCELLATION_START] Demande annulation",
            extra={
                'transaction_uuid': transaction_uuid,
                'reason': reason
            }
        )

        result = self._make_request('POST', endpoint, data=payload)

        if result['success']:
            data = result['data']
            logger.info(
                "[MOBCASH] [REQUEST_CANCELLATION_SUCCESS] Demande créée",
                extra={
                    'cancellation_id': data.get('id'),
                    'transaction_id': data.get('transaction_id'),
                    'status': data.get('status')
                }
            )
        else:
            logger.error(
                "[MOBCASH] [REQUEST_CANCELLATION_FAILED] Échec demande",
                extra={'error': result.get('error')}
            )

        return result

    # ========================================================================
    # VOIR DEMANDE ANNULATION POUR UNE TRANSACTION
    # ========================================================================

    def get_cancellation_request(self, transaction_uuid: str) -> Dict[str, Any]:
        """
        Récupérer la demande d'annulation d'une transaction

        GET /api/v1/transactions/list/{uuid}/cancellation-request/

        Args:
            transaction_uuid: UUID de la transaction

        Returns:
            Dict avec 'success', 'data' contenant CancellationRequest
        """
        endpoint = f'/api/v1/transactions/list/{transaction_uuid}/cancellation-request/'

        logger.info(
            "[MOBCASH] [GET_CANCELLATION_START] Récupération demande annulation",
            extra={'transaction_uuid': transaction_uuid}
        )

        result = self._make_request('GET', endpoint)

        if result['success']:
            data = result['data']
            logger.info(
                "[MOBCASH] [GET_CANCELLATION_SUCCESS] Demande récupérée",
                extra={
                    'status': data.get('status'),
                    'requested_at': data.get('requested_at')
                }
            )
        else:
            logger.warning(
                "[MOBCASH] [GET_CANCELLATION_FAILED] Pas de demande trouvée",
                extra={'error': result.get('error')}
            )

        return result

    # ========================================================================
    # LISTER TOUTES LES DEMANDES ANNULATION USER
    # ========================================================================

    def list_all_cancellation_requests(
            self,
            page: int = 1,
            page_size: int = 20,
            status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lister toutes les demandes d'annulation de l'utilisateur

        GET /api/v1/transactions/user-all-cancellation-requests/

        Args:
            page: Numéro de page
            page_size: Nombre d'éléments par page
            status: Filtrer par statut (PENDING, APPROVED, REJECTED)

        Returns:
            Dict avec 'success', 'data' contenant:
            {
                'count': int,
                'total_pages': int,
                'current_page': int,
                'page_size': int,
                'next': bool,
                'previous': bool,
                'stats': {
                    'total': int,
                    'pending': int,
                    'approved': int,
                    'rejected': int
                },
                'results': [...]
            }
        """
        endpoint = '/api/v1/transactions/user-all-cancellation-requests/'

        params = {
            'page': page,
            'page_size': page_size
        }

        if status:
            params['status'] = status.upper()

        logger.info(
            "[MOBCASH] [LIST_CANCELLATIONS_START] Liste demandes annulation",
            extra={'page': page, 'page_size': page_size, 'status': status}
        )

        result = self._make_request('GET', endpoint, params=params)

        if result['success']:
            data = result['data']
            stats = data.get('stats', {})
            logger.info(
                "[MOBCASH] [LIST_CANCELLATIONS_SUCCESS] Liste récupérée",
                extra={
                    'count': data.get('count'),
                    'pending': stats.get('pending'),
                    'approved': stats.get('approved'),
                    'rejected': stats.get('rejected')
                }
            )

        return result

    # ========================================================================
    # HELPERS & UTILITIES
    # ========================================================================

    def check_connection(self) -> bool:
        """
        Vérifier la connexion au backend MobCash

        Fait un appel simple pour tester l'authentification

        Returns:
            True si la connexion fonctionne, False sinon
        """
        logger.info("[MOBCASH] [CHECK_CONNECTION] Test de connexion")

        # Faire un appel simple (liste transactions avec page_size=1)
        result = self.list_transactions(page=1, page_size=1)

        if result['success']:
            logger.info("[MOBCASH] [CHECK_CONNECTION_SUCCESS] Connexion OK")
            return True
        else:
            logger.error(
                "[MOBCASH] [CHECK_CONNECTION_FAILED] Connexion KO",
                extra={'error': result.get('error')}
            )
            return False

    def get_transaction_status(self, transaction_uuid: str) -> Optional[str]:
        """
        Récupérer rapidement le statut d'une transaction

        Args:
            transaction_uuid: UUID de la transaction

        Returns:
            Statut de la transaction ou None si erreur
        """
        result = self.get_transaction_by_uuid(transaction_uuid)

        if result['success']:
            return result['data'].get('status')

        return None

    def is_transaction_completed(self, transaction_uuid: str) -> bool:
        """
        Vérifier si une transaction est complétée

        Args:
            transaction_uuid: UUID de la transaction

        Returns:
            True si COMPLETED, False sinon
        """
        status = self.get_transaction_status(transaction_uuid)
        return status == 'COMPLETED'

    def is_transaction_failed(self, transaction_uuid: str) -> bool:
        """
        Vérifier si une transaction a échoué

        Args:
            transaction_uuid: UUID de la transaction

        Returns:
            True si FAILED, False sinon
        """
        status = self.get_transaction_status(transaction_uuid)
        return status == 'FAILED'

    # ========================================================================
    # RÉCUPÉRER LE SOLDE DU WALLET
    # ========================================================================

    def get_wallet_balance(self) -> float:
        """
        Récupérer le solde du wallet MobCash

        GET /api/v1/wallets/balance/

        Returns:
            float: Le solde du wallet en float, 0.0 en cas d'erreur
        """
        endpoint = "/api/v1/wallets/balance/"

        logger.info(
            "[MOBCASH] [GET_WALLET_BALANCE_START] Récupération du solde du wallet"
        )

        result = self._make_request("GET", endpoint)

        if result.get("success"):
            data = result.get("data", {})
            balance_str = data.get("balance", "0.00")
            
            try:
                balance = float(balance_str)
                logger.info(
                    "[MOBCASH] [GET_WALLET_BALANCE_SUCCESS] Solde récupéré",
                    extra={
                        "balance": balance,
                        "currency": data.get("currency"),
                        "user_email": data.get("user_email")
                    }
                )
                return balance
            except (ValueError, TypeError) as e:
                logger.error(
                    "[MOBCASH] [GET_WALLET_BALANCE_ERROR] Erreur de conversion du solde",
                    extra={
                        "error": str(e),
                        "balance_str": balance_str
                    }
                )
                return 0.0
        else:
            logger.error(
                "[MOBCASH] [GET_WALLET_BALANCE_FAILED] Échec récupération solde",
                extra={"error": result.get("error")}
            )
            return 0.0

    def create_recharge_request_from_request(
        self, request_data: Dict
    ) -> Dict[str, Any]:
        """
        Créer une demande de recharge de balance Mobcash en passant directement les données de la requête

        POST /api/v1/wallets/recharge-requests/

        Args:
            request_data: Données de la requête (request.data)

        Returns:
            Dict avec 'success', 'data', 'error', etc.
        """
        endpoint = "/api/v1/wallets/recharge-requests/"
        request_data["payment_proof"]=None 
        request_data["payment_proof_url"] = request_data.get("payment_proof")
        result = self._make_request("POST", endpoint, data=request_data)

        return result
        
