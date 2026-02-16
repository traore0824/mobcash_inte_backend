def total_amount_to_send_wave(montant_souhaite):
    """
    Calcule combien il faut envoyer pour que le destinataire reçoive `montant_souhaite`
    après déduction des frais Wave.
    """
    montant = montant_souhaite
    while True:
        frais = fee_wave(montant)
        recu = montant - frais
        if montant_souhaite <= recu <= montant_souhaite + 1:
            return int(montant)
        montant += 1  # on essaie un peu plus jusqu’à atteindre la bonne valeur


def fee_wave(montant):
    """Calcule 1% arrondi au multiple de 5 supérieur"""
    frais = montant * 0.01
    if frais % 5 != 0:
        frais = ((frais // 5) + 1) * 5
    return int(frais)


print(fee_wave(1000))
