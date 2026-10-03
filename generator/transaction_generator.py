"""Synthetic transaction generator for individual banking customers."""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from models.customer import CustomerProfile
from models.transaction import Transaction
from generator.scenarios import (
    generate_normal_transactions,
    inject_structuring_scenario,
    inject_money_mule_scenario,
    inject_sanction_corridor_scenario,
    inject_dormancy_burst_scenario,
    inject_account_takeover_scenario,
    inject_card_fraud_testing_scenario,
    inject_app_scam_scenario,
    inject_bust_out_fraud_scenario,
    inject_sim_swap_scenario,
    inject_friendly_fraud_scenario,
    inject_bin_attack_scenario,
    inject_bec_impersonation_scenario,
    inject_aitm_session_hijack_scenario,
    inject_overpayment_scam_scenario,
    inject_tbml_scenario,
    inject_fan_out_layering_scenario,
    inject_cuckoo_smurfing_scenario,
    inject_crypto_mixer_scenario,
    inject_human_trafficking_scenario,
    inject_loan_wash_scenario
)

class TransactionGenerator:
    """Generates continuous streams of banking transactions for customer cohorts."""

    def __init__(self, seed: Optional[int] = 42):
        if seed is not None:
            random.seed(seed)
        self.global_tx_counter = 100000

    def generate_customer_transactions(
        self,
        customer: CustomerProfile,
        days_history: int = 90,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """Generates realistic transaction history for an individual customer."""
        if end_date is None:
            end_date = datetime.now()
        start_date = end_date - timedelta(days=days_history)

        txs: List[Transaction] = []

        # 1. Base transactions (normal spending, salary, utilities)
        # Note: if customer is a dormant account, start normal activity later or omit
        if customer.archetype == "STUDENT_MONEY_MULE":
            # Very low baseline activity for money mules
            base_txs = generate_normal_transactions(
                customer, 
                start_date, 
                end_date, 
                self.global_tx_counter
            )
            self.global_tx_counter += len(base_txs)
            txs.extend(base_txs[:max(4, len(base_txs) // 3)])
        else:
            base_txs = generate_normal_transactions(
                customer, 
                start_date, 
                end_date, 
                self.global_tx_counter
            )
            self.global_tx_counter += len(base_txs)
            txs.extend(base_txs)

        # 2. Inject typologies based on customer archetype
        mid_point_date = start_date + timedelta(days=days_history // 2)

        if customer.archetype == "STRUCTURING_CASH_OPERATOR":
            struct_txs = inject_structuring_scenario(customer, mid_point_date, self.global_tx_counter)
            self.global_tx_counter += len(struct_txs)
            txs.extend(struct_txs)

        elif customer.archetype == "STUDENT_MONEY_MULE":
            mule_date = start_date + timedelta(days=int(days_history * 0.75))
            mule_txs = inject_money_mule_scenario(customer, mule_date, self.global_tx_counter)
            self.global_tx_counter += len(mule_txs)
            txs.extend(mule_txs)

        elif customer.archetype == "SANCTION_GREYLIST_CORRIDOR":
            corridor_date = start_date + timedelta(days=int(days_history * 0.40))
            corridor_txs = inject_sanction_corridor_scenario(customer, corridor_date, self.global_tx_counter)
            self.global_tx_counter += len(corridor_txs)
            txs.extend(corridor_txs)

        elif customer.archetype == "ADVERSE_MEDIA_FINANCIAL_CRIME":
            # Combines high risk corridor and structuring/crypto
            burst_date = start_date + timedelta(days=int(days_history * 0.60))
            burst_txs = inject_dormancy_burst_scenario(customer, burst_date, self.global_tx_counter)
            self.global_tx_counter += len(burst_txs)
            txs.extend(burst_txs)

        elif customer.archetype == "ACCOUNT_TAKEOVER_VICTIM":
            ato_date = start_date + timedelta(days=int(days_history * 0.85))
            ato_txs = inject_account_takeover_scenario(customer, ato_date, self.global_tx_counter)
            self.global_tx_counter += len(ato_txs)
            txs.extend(ato_txs)

        elif customer.archetype == "CARD_FRAUD_VICTIM":
            card_date = start_date + timedelta(days=int(days_history * 0.70))
            card_txs = inject_card_fraud_testing_scenario(customer, card_date, self.global_tx_counter)
            self.global_tx_counter += len(card_txs)
            txs.extend(card_txs)

        elif customer.archetype == "APP_SCAM_VICTIM":
            scam_date = start_date + timedelta(days=int(days_history * 0.80))
            scam_txs = inject_app_scam_scenario(customer, scam_date, self.global_tx_counter)
            self.global_tx_counter += len(scam_txs)
            txs.extend(scam_txs)

        elif customer.archetype == "FIRST_PARTY_BUST_OUT":
            bust_date = start_date + timedelta(days=int(days_history * 0.65))
            bust_txs = inject_bust_out_fraud_scenario(customer, bust_date, self.global_tx_counter)
            self.global_tx_counter += len(bust_txs)
            txs.extend(bust_txs)

        elif customer.archetype == "SIM_SWAP_VICTIM":
            sim_date = start_date + timedelta(days=int(days_history * 0.88))
            sim_txs = inject_sim_swap_scenario(customer, sim_date, self.global_tx_counter)
            self.global_tx_counter += len(sim_txs)
            txs.extend(sim_txs)

        elif customer.archetype == "FRIENDLY_FRAUD_ABUSER":
            ff_date = start_date + timedelta(days=int(days_history * 0.50))
            ff_txs = inject_friendly_fraud_scenario(customer, ff_date, self.global_tx_counter)
            self.global_tx_counter += len(ff_txs)
            txs.extend(ff_txs)

        elif customer.archetype == "BIN_ATTACK_TARGET":
            bin_date = start_date + timedelta(days=int(days_history * 0.72))
            bin_txs = inject_bin_attack_scenario(customer, bin_date, self.global_tx_counter)
            self.global_tx_counter += len(bin_txs)
            txs.extend(bin_txs)

        elif customer.archetype == "BEC_EXECUTIVE_TARGET":
            bec_date = start_date + timedelta(days=int(days_history * 0.80))
            bec_txs = inject_bec_impersonation_scenario(customer, bec_date, self.global_tx_counter)
            self.global_tx_counter += len(bec_txs)
            txs.extend(bec_txs)

        elif customer.archetype == "AITM_PHISHING_VICTIM":
            aitm_date = start_date + timedelta(days=int(days_history * 0.82))
            aitm_txs = inject_aitm_session_hijack_scenario(customer, aitm_date, self.global_tx_counter)
            self.global_tx_counter += len(aitm_txs)
            txs.extend(aitm_txs)

        elif customer.archetype == "OVERPAYMENT_SCAM_VICTIM":
            ovp_date = start_date + timedelta(days=int(days_history * 0.60))
            ovp_txs = inject_overpayment_scam_scenario(customer, ovp_date, self.global_tx_counter)
            self.global_tx_counter += len(ovp_txs)
            txs.extend(ovp_txs)

        elif customer.archetype == "TBML_FRONT_OPERATOR":
            tbml_date = start_date + timedelta(days=int(days_history * 0.45))
            tbml_txs = inject_tbml_scenario(customer, tbml_date, self.global_tx_counter)
            self.global_tx_counter += len(tbml_txs)
            txs.extend(tbml_txs)

        elif customer.archetype == "FAN_OUT_LAYERING_NETWORK":
            fan_date = start_date + timedelta(days=int(days_history * 0.55))
            fan_txs = inject_fan_out_layering_scenario(customer, fan_date, self.global_tx_counter)
            self.global_tx_counter += len(fan_txs)
            txs.extend(fan_txs)

        elif customer.archetype == "CUCKOO_SMURFING_RECIPIENT":
            cuckoo_date = start_date + timedelta(days=int(days_history * 0.60))
            cuckoo_txs = inject_cuckoo_smurfing_scenario(customer, cuckoo_date, self.global_tx_counter)
            self.global_tx_counter += len(cuckoo_txs)
            txs.extend(cuckoo_txs)

        elif customer.archetype == "CRYPTO_MIXER_OPERATOR":
            mixer_date = start_date + timedelta(days=int(days_history * 0.70))
            mixer_txs = inject_crypto_mixer_scenario(customer, mixer_date, self.global_tx_counter)
            self.global_tx_counter += len(mixer_txs)
            txs.extend(mixer_txs)

        elif customer.archetype == "HUMAN_TRAFFICKING_RING":
            ht_date = start_date + timedelta(days=int(days_history * 0.50))
            ht_txs = inject_human_trafficking_scenario(customer, ht_date, self.global_tx_counter)
            self.global_tx_counter += len(ht_txs)
            txs.extend(ht_txs)

        elif customer.archetype == "LOAN_WASH_BORROWER":
            loan_date = start_date + timedelta(days=int(days_history * 0.35))
            loan_txs = inject_loan_wash_scenario(customer, loan_date, self.global_tx_counter)
            self.global_tx_counter += len(loan_txs)
            txs.extend(loan_txs)

        # Sort all transactions chronologically by timestamp
        txs.sort(key=lambda t: t.timestamp)
        return txs

    def generate_cohort_transactions(
        self,
        customers: List[CustomerProfile],
        days_history: int = 90
    ) -> Dict[str, List[Transaction]]:
        """Generates transactions mapped by customer_id."""
        cohort_txs: Dict[str, List[Transaction]] = {}
        for cust in customers:
            cohort_txs[cust.customer_id] = self.generate_customer_transactions(cust, days_history=days_history)
        return cohort_txs
