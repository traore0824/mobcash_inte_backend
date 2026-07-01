import math


def fee_wave(montant: int) -> int:
    """Calcule les frais Wave : 1% du montant envoyé, arrondi au multiple de 5 supérieur."""
    return math.ceil(montant * 0.01 / 5) * 5


def total_amount_to_send_wave(montant_souhaite: int) -> int:
    """
    Calcule le montant total que l'expéditeur doit payer pour que
    le destinataire reçoive au moins `montant_souhaite` (tolérance +1 F max).

    Retourne uniquement : total_expediteur
    """
    montant_envoye = montant_souhaite
    while True:
        frais = fee_wave(montant_envoye)
        recu = montant_envoye  # le destinataire reçoit le montant envoyé
        total_expediteur = montant_envoye + frais

        if recu >= montant_souhaite:
            return total_expediteur  # juste le total payé par l'expéditeur

        montant_envoye += 1  # on teste le prochain montant


# # 🔥 Tests
# print(total_amount_to_send_wave(1000))  # 1010
# print(total_amount_to_send_wave(8973))  # 9063
# print(total_amount_to_send_wave(2500))  # 2530
# print(total_amount_to_send_wave(5200))  # 5255



