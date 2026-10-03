"""AML typology scenario generators for transaction streams."""

import random
from datetime import datetime, timedelta
from typing import List
from models.transaction import Transaction, TransactionType, TransactionDirection
from models.customer import CustomerProfile

def generate_normal_transactions(
    customer: CustomerProfile,
    start_date: datetime,
    end_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """Generates baseline regular retail banking transactions."""
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    
    total_days = max(1, (end_date - start_date).days)
    monthly_salary = customer.annual_income_usd / 12.0
    
    # 1. Monthly Payroll / Income credits
    cur_date = start_date
    while cur_date <= end_date:
        # Salary arrives on 25th of month (or 1st)
        if cur_date.day in [1, 25]:
            tx_id = f"TXN-{current_tx_id:07d}"
            current_tx_id += 1
            amount = round(monthly_salary * random.uniform(0.95, 1.05), 2)
            txs.append(Transaction(
                transaction_id=tx_id,
                customer_id=customer.customer_id,
                timestamp=cur_date.replace(hour=8, minute=30, second=0).isoformat(),
                transaction_type=TransactionType.SALARY_CREDIT if customer.employer_name else TransactionType.ACH_DEPOSIT,
                direction=TransactionDirection.INBOUND,
                amount_usd=amount,
                counterparty_name=customer.employer_name or "State Pension Disbursing Agency",
                counterparty_country=customer.residence_country,
                counterparty_category="EMPLOYER" if customer.employer_name else "GOVERNMENT",
                channel="ACH",
                reference_narrative="Direct Payroll Deposit / Net Earnings",
                is_suspicious_synthetic=False
            ))
            
            # Rent/Mortgage payment 3 days after salary
            rent_date = cur_date + timedelta(days=3)
            if rent_date <= end_date:
                tx_id = f"TXN-{current_tx_id:07d}"
                current_tx_id += 1
                rent_amount = round(monthly_salary * random.uniform(0.25, 0.40), 2)
                txs.append(Transaction(
                    transaction_id=tx_id,
                    customer_id=customer.customer_id,
                    timestamp=rent_date.replace(hour=10, minute=15).isoformat(),
                    transaction_type=TransactionType.ACH_WITHDRAWAL,
                    direction=TransactionDirection.OUTBOUND,
                    amount_usd=rent_amount,
                    counterparty_name="Metropolitan Residential Property Management",
                    counterparty_country=customer.residence_country,
                    counterparty_category="UTILITY",
                    channel="ACH",
                    reference_narrative="Monthly Housing / Rent Payment",
                    is_suspicious_synthetic=False
                ))
                
        cur_date += timedelta(days=1)
        
    # 2. Living expenses: groceries, dining, coffee, fuel (2-4 per week)
    spend_merchants = [
        ("Whole Foods Market", "RETAILER", "Groceries & Household"),
        ("Tesco Superstore", "RETAILER", "Supermarket Retail"),
        ("Starbucks Coffee", "RETAILER", "Food & Beverage"),
        ("Amazon Digital Retail", "RETAILER", "Online Household Purchase"),
        ("Shell Service Station", "RETAILER", "Fuel & Automotive"),
        ("Local Pharmacy Healthcare", "RETAILER", "Pharmacy / Health"),
        ("Uber Mobility", "RETAILER", "Urban Ride Transportation"),
        ("City Power & Water", "UTILITY", "Monthly Municipal Utility Bill"),
    ]
    
    for day_offset in range(total_days):
        day_date = start_date + timedelta(days=day_offset)
        # Randomly spend on 40% of days
        if random.random() < 0.40:
            num_spends = random.choice([1, 2])
            for _ in range(num_spends):
                merchant, cat, narr = random.choice(spend_merchants)
                tx_id = f"TXN-{current_tx_id:07d}"
                current_tx_id += 1
                
                # Living expense spend amounts proportional to income
                base_spend = random.uniform(12.50, 180.0)
                if customer.annual_income_usd > 200000:
                    base_spend *= 2.5
                amount = round(base_spend, 2)
                
                tx_type = TransactionType.POS_PURCHASE if cat == "RETAILER" else TransactionType.ACH_WITHDRAWAL
                ch = "POS_TERMINAL" if cat == "RETAILER" else "WEB_PORTAL"
                card_mode = "CHIP_EMV" if ch == "POS_TERMINAL" else "CNP_ECOMMERCE"
                
                txs.append(Transaction(
                    transaction_id=tx_id,
                    customer_id=customer.customer_id,
                    timestamp=day_date.replace(hour=random.randint(9, 21), minute=random.randint(0, 59)).isoformat(),
                    transaction_type=tx_type,
                    direction=TransactionDirection.OUTBOUND,
                    amount_usd=amount,
                    counterparty_name=merchant,
                    counterparty_country=customer.residence_country,
                    counterparty_category=cat,
                    channel=ch,
                    reference_narrative=narr,
                    device_id=customer.device_primary_id,
                    ip_address=customer.primary_ip_address,
                    ip_country=customer.primary_ip_country,
                    is_card_present=(ch == "POS_TERMINAL"),
                    card_entry_mode=card_mode,
                    auth_status="AUTHORIZED",
                    is_suspicious_synthetic=False,
                    is_fraud_synthetic=False
                ))
                
    return txs

def inject_structuring_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Typology: Structuring / Smurfing.
    Customer deposits multiple cash tranches just under the $10,000 CTR reporting threshold
    (e.g., $9,200, $9,500, $9,800, $8,900) across 5 to 10 days.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    
    num_deposits = random.randint(3, 5)
    for i in range(num_deposits):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        
        tx_date = anchor_date + timedelta(days=i * 2 + random.randint(0, 1))
        # Structuring amounts specifically in $8,200 - $9,900 range
        amount = round(random.choice([8500.0, 9200.0, 9450.0, 9700.0, 9850.0, 8900.0, 9600.0]) + random.uniform(0, 80), 2)
        
        branch = f"Branch Teller #{random.randint(101, 109)} - Cash Counter"
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=tx_date.replace(hour=random.randint(10, 15), minute=random.randint(10, 50)).isoformat(),
            transaction_type=TransactionType.CASH_DEPOSIT,
            direction=TransactionDirection.INBOUND,
            amount_usd=amount,
            counterparty_name=branch,
            counterparty_country=customer.residence_country,
            counterparty_category="ATM_BRANCH",
            channel="BRANCH_TELLER",
            reference_narrative="Over-the-counter cash deposit / Personal savings allocation",
            is_suspicious_synthetic=True,
            synthetic_typology_tag="STRUCTURING_SMURFING"
        ))
        
    return txs

def inject_money_mule_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Typology: Money Mule / Rapid Movement of Funds.
    Account receives high-value inbound wire and dissipates 90%+ within 24-48 hours
    to crypto exchanges or outbound international wire.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    
    inflow_amount = round(random.uniform(18000.0, 45000.0), 2)
    inflow_date = anchor_date
    
    # 1. Inbound large wire
    tx_id_in = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_in,
        customer_id=customer.customer_id,
        timestamp=inflow_date.replace(hour=9, minute=15).isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_IN,
        direction=TransactionDirection.INBOUND,
        amount_usd=inflow_amount,
        counterparty_name="Apex Global Consulting FZE",
        counterparty_country="AE",
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Payment for International Contract Services Ref 7721",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="MULE_INBOUND_SPIKE"
    ))
    
    # 2. Outflow within 24-36 hours (e.g. 92% of funds sent to crypto exchange or overseas)
    drain_amount = round(inflow_amount * random.uniform(0.90, 0.96), 2)
    outflow_date = inflow_date + timedelta(hours=random.randint(12, 34))
    
    tx_id_out = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_out,
        customer_id=customer.customer_id,
        timestamp=outflow_date.isoformat(),
        transaction_type=TransactionType.CRYPTO_PURCHASE,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=drain_amount,
        counterparty_name="Binance P2P / Virtual Asset Ramp",
        counterparty_country="SC", # Seychelles
        counterparty_category="CRYPTO_EXCHANGE",
        channel="WEB_PORTAL",
        reference_narrative="USDT Purchase Settlement #88192301",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="MULE_RAPID_DISSIPATION"
    ))
    
    return txs

def inject_sanction_corridor_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Typology: High-Risk Jurisdiction / Sanctioned Country Wire Activity.
    Direct transactions with entities located in FATF Greylist/Blacklist or Secrecy havens.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    
    high_risk_jurisdictions = [
        ("SY", "Damascus Commercial Logistics Ltd", "SYRIA_COMMERCIAL"),
        ("IR", "Tehran General Mercantile Co", "IRAN_TRANSIT"),
        ("MM", "Yangon Gemstones Trade Syndicate", "MYANMAR_MINING"),
        ("KY", "Cayman Starburst Offshore Fund", "CAYMAN_SECRECY"),
        ("VG", "Tortola Nominee Holdings Corp", "BVI_SHELL"),
        ("YE", "Sana'a Humanitarian Transport Line", "YEMEN_RELIEF"),
    ]
    
    num_txs = random.randint(2, 4)
    for i in range(num_txs):
        country, cp_name, tag = random.choice(high_risk_jurisdictions)
        direction = random.choice([TransactionDirection.INBOUND, TransactionDirection.OUTBOUND])
        tx_type = TransactionType.INTERNATIONAL_WIRE_IN if direction == TransactionDirection.INBOUND else TransactionType.INTERNATIONAL_WIRE_OUT
        
        amount = round(random.uniform(14000.0, 75000.0), 2)
        tx_date = anchor_date + timedelta(days=i * 6 + random.randint(1, 3))
        
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=tx_date.replace(hour=14, minute=20).isoformat(),
            transaction_type=tx_type,
            direction=direction,
            amount_usd=amount,
            counterparty_name=cp_name,
            counterparty_country=country,
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative=f"Cross-border settlement via correspondent bank / {tag}",
            is_suspicious_synthetic=True,
            synthetic_typology_tag=f"HIGH_RISK_CORRIDOR_{country}"
        ))
        
    return txs

def inject_dormancy_burst_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Typology: Dormancy Break & Sudden Spike.
    Account with previous silence suddenly experiences high-velocity wires.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    
    burst_amounts = [15000.0, 22000.0, 31000.0]
    for i, amt in enumerate(burst_amounts):
        tx_date = anchor_date + timedelta(hours=i * 18 + 4)
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=tx_date.isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=amt,
            counterparty_name=f"Private Escrow Trust Alpha {i+1}",
            counterparty_country=customer.residence_country,
            counterparty_category="INDIVIDUAL",
            channel="WEB_PORTAL",
            reference_narrative="Settlement proceeds urgent release",
            is_suspicious_synthetic=True,
            synthetic_typology_tag="DORMANCY_BREAK_SURGE"
        ))
        
    return txs

# ==========================================
# FRAUD TYPOLOGY INJECTORS
# ==========================================

def inject_account_takeover_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology: Account Takeover (ATO) & Impossible Travel.
    Legitimate login in home country, followed within 45 minutes by login & wire
    from an unauthorized overseas proxy on a new device.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # 1. Legitimate normal card or login transaction at home
    t1_date = anchor_date
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=t1_date.replace(hour=14, minute=10).isoformat(),
        transaction_type=TransactionType.POS_PURCHASE,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=42.50,
        counterparty_name="Local Metro Supermarket",
        counterparty_country=customer.residence_country,
        counterparty_category="RETAILER",
        channel="POS_TERMINAL",
        reference_narrative="Customer in-store grocery purchase",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        is_card_present=True,
        card_entry_mode="CHIP_EMV",
        auth_status="AUTHORIZED",
        is_fraud_synthetic=False
    ))

    # 2. Hostile ATO drain 35 minutes later from foreign IP on unknown device
    t2_date = t1_date.replace(hour=14, minute=45)
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    drain_amount = round(random.uniform(7500.0, 16000.0), 2)
    hostile_ip = f"185.{random.randint(100, 250)}.{random.randint(10, 240)}.{random.randint(1, 250)}"
    hostile_country = "NG" if customer.residence_country != "NG" else "RU"

    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=t2_date.isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=drain_amount,
        counterparty_name="FastPay Global Clearing Ltd",
        counterparty_country="SC",
        counterparty_category="CRYPTO_EXCHANGE",
        channel="WEB_PORTAL",
        reference_narrative="Urgent external balance transfer to unverified wallet",
        device_id="DEV-UNKNOWN-ATTACKER-99X",
        ip_address=hostile_ip,
        ip_country=hostile_country,
        is_card_present=False,
        auth_status="AUTHORIZED",
        is_new_payee=True,
        payee_first_seen_hours=0.2,
        is_fraud_synthetic=True,
        fraud_typology_tag="ATO_IMPOSSIBLE_TRAVEL"
    ))

    return txs

def inject_card_fraud_testing_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology: Card Testing / Micro-probing followed by High-Dollar Drain.
    Card details compromised via e-commerce breach. Attacker runs 2 tiny authorizations
    to verify card is active, followed immediately by high-value CNP purchase.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_start = anchor_date.replace(hour=3, minute=12) # Early morning probe

    # 2 micro-probes
    probes = [0.89, 1.45]
    for i, amt in enumerate(probes):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_probe = t_start + timedelta(minutes=i * 4)
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=t_probe.isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name=f"Digital Content Test Service #{i+1}",
            counterparty_country="US",
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            reference_narrative="Trial digital verification charge",
            device_id="DEV-BOTNET-CLONE-441",
            ip_address="194.26.29.112",
            ip_country="NL",
            is_card_present=False,
            card_entry_mode="CNP_ECOMMERCE",
            auth_status="AUTHORIZED",
            is_fraud_synthetic=True,
            fraud_typology_tag="CARD_TESTING_MICRO_PROBE"
        ))

    # High-dollar drain 18 minutes later
    tx_id_drain = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    t_drain = t_start + timedelta(minutes=18)
    drain_amt = round(random.uniform(2400.0, 4800.0), 2)
    txs.append(Transaction(
        transaction_id=tx_id_drain,
        customer_id=customer.customer_id,
        timestamp=t_drain.isoformat(),
        transaction_type=TransactionType.ONLINE_PURCHASE,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=drain_amt,
        counterparty_name="Luxe High-End Electronics Direct",
        counterparty_country="HK",
        counterparty_category="RETAILER",
        channel="WEB_PORTAL",
        reference_narrative="Expedited luxury consumer tech order",
        device_id="DEV-BOTNET-CLONE-441",
        ip_address="194.26.29.112",
        ip_country="NL",
        is_card_present=False,
        card_entry_mode="CNP_ECOMMERCE",
        auth_status="DECLINED_SUSPECTED_FRAUD",
        is_fraud_synthetic=True,
        fraud_typology_tag="CARD_FRAUD_HIGH_VALUE_DRAIN"
    ))

    return txs

def inject_app_scam_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology: Authorized Push Payment (APP) / Investment or Romance Scam.
    Customer is manipulated into sending urgent high-value transfers to brand new payees.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    scam_transfers = [
        (6500.0, "Global Alpha Arbitrage Pool Ltd", "Urgent guaranteed return investment enrollment ref #9981"),
        (9800.0, "VIP Capital Liquidators Escrow", "Top-up balance to release guaranteed trade profits"),
    ]

    for i, (amt, cp_name, narrative) in enumerate(scam_transfers):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_tx = anchor_date + timedelta(days=i * 2 + 1, hours=11, minutes=30)

        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=t_tx.isoformat(),
            transaction_type=TransactionType.P2P_TRANSFER_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name=cp_name,
            counterparty_country="GB",
            counterparty_category="INDIVIDUAL",
            channel="MOBILE_APP",
            reference_narrative=narrative,
            device_id=customer.device_primary_id,
            ip_address=customer.primary_ip_address,
            ip_country=customer.primary_ip_country,
            is_new_payee=True,
            payee_first_seen_hours=0.5,
            auth_status="AUTHORIZED",
            is_fraud_synthetic=True,
            fraud_typology_tag="APP_INVESTMENT_SCAM"
        ))

    return txs

def inject_bust_out_fraud_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology: First-Party Bust-Out / Deposit Kiting Fraud.
    Customer deposits large fraudulent ACH, then immediately rushes to withdraw maximum
    cash at ATMs and outbound P2P transfers before the check/ACH returns unpaid.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # 1. Bogus ACH deposit
    tx_id_in = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    t_in = anchor_date.replace(hour=9, minute=0)
    txs.append(Transaction(
        transaction_id=tx_id_in,
        customer_id=customer.customer_id,
        timestamp=t_in.isoformat(),
        transaction_type=TransactionType.ACH_DEPOSIT,
        direction=TransactionDirection.INBOUND,
        amount_usd=9850.0,
        counterparty_name="Apex External Bank Link",
        counterparty_country=customer.residence_country,
        counterparty_category="INDIVIDUAL",
        channel="WEB_PORTAL",
        reference_narrative="ACH External Link Inbound Transfer",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="BUST_OUT_KITED_DEPOSIT"
    ))

    # 2. Repeated maximal cash/P2P drains in next 18 hours
    drains = [
        (1000.0, TransactionType.ATM_WITHDRAWAL, "ATM Cash Out #4401 - Downtown 24h", "ATM"),
        (1000.0, TransactionType.ATM_WITHDRAWAL, "ATM Cash Out #4402 - Metro Center", "ATM"),
        (3800.0, TransactionType.P2P_TRANSFER_OUT, "QuickCash Peer Transfer Account", "MOBILE_APP"),
        (3500.0, TransactionType.P2P_TRANSFER_OUT, "Express Liquidity Transfer", "MOBILE_APP"),
    ]

    for i, (amt, tx_type, cp_name, ch) in enumerate(drains):
        tx_id_out = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_out = t_in + timedelta(hours=i * 3 + 2)
        txs.append(Transaction(
            transaction_id=tx_id_out,
            customer_id=customer.customer_id,
            timestamp=t_out.isoformat(),
            transaction_type=tx_type,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name=cp_name,
            counterparty_country=customer.residence_country,
            counterparty_category="PEER" if tx_type == TransactionType.P2P_TRANSFER_OUT else "ATM",
            channel=ch,
            reference_narrative="Immediate cash extraction prior to settlement",
            device_id=customer.device_primary_id,
            ip_address=customer.primary_ip_address,
            ip_country=customer.primary_ip_country,
            is_new_payee=True,
            auth_status="AUTHORIZED",
            is_fraud_synthetic=True,
            fraud_typology_tag="BUST_OUT_RAPID_DRAIN"
        ))

    return txs

# ==========================================
# ADDITIONAL FRAUD & AML TYPOLOGY INJECTORS
# ==========================================

def inject_sim_swap_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-06: SIM Swap & Credential Reset Outbound Drain.
    Adversary executes unauthorized SIM swap, resets online banking credentials,
    adds a new beneficiary and immediately drains funds via wire.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_start = anchor_date.replace(hour=11, minute=20)

    drain_amt = round(random.uniform(4800.0, 9500.0), 2)
    tx_id = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1

    txs.append(Transaction(
        transaction_id=tx_id,
        customer_id=customer.customer_id,
        timestamp=(t_start + timedelta(minutes=24)).isoformat(),
        transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=drain_amt,
        counterparty_name="NeoBank Digital Escrow LLC",
        counterparty_country=customer.residence_country,
        counterparty_category="OFFSHORE_CORP",
        channel="MOBILE_APP",
        reference_narrative="SIM Swap MFA reset detected: Urgent balance evacuation to external account",
        device_id="DEV-ROGUE-HANDSET-88A",
        ip_address="172.56.21.99",
        ip_country=customer.residence_country,
        is_new_payee=True,
        payee_first_seen_hours=0.4,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="SIM_SWAP_DRAIN"
    ))

    return txs

def inject_friendly_fraud_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-07: Friendly Fraud / Systematic Chargeback & Dispute Abuse.
    Customer orders expensive luxury/digital goods from trusted home device, then files
    fraudulent chargeback claims claiming unauthorized activity or non-receipt.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    claims = [
        (620.0, "ElectroHub Consumer Tech", "Dispute: Unauthorized transaction claim filed by cardholder"),
        (890.0, "Designer Apparel Direct", "Dispute: Goods not received claim filed after verified 3DS delivery"),
        (1350.0, "Luxury Watches Online", "Chargeback: Cardholder claims stolen identity despite chip verification")
    ]

    for i, (amt, merchant, narr) in enumerate(claims):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_tx = anchor_date + timedelta(days=i * 4 + 1, hours=15, minutes=10)

        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=t_tx.isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name=merchant,
            counterparty_country=customer.residence_country,
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            reference_narrative=narr,
            device_id=customer.device_primary_id,
            ip_address=customer.primary_ip_address,
            ip_country=customer.primary_ip_country,
            is_card_present=False,
            card_entry_mode="CNP_ECOMMERCE",
            auth_status="AUTHORIZED",
            is_fraud_synthetic=True,
            fraud_typology_tag="FRIENDLY_FRAUD_DISPUTE"
        ))

    return txs

def inject_bin_attack_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-08: Automated BIN Attack & Card Testing Velocity.
    Botnet fires rapid authorization requests with incrementing CVV/expiry combinations.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_start = anchor_date.replace(hour=2, minute=15)

    attempts = [
        (1.99, "DECLINED_INVALID_CVV", "CVV Mismatch - automated payment gateway test #1"),
        (2.49, "DECLINED_EXPIRED", "Expired card error - botnet script test #2"),
        (1.85, "DECLINED_SUSPECTED_FRAUD", "Velocity rule block - automated script test #3"),
        (850.0, "AUTHORIZED", "High value consumer electronic purchase following brute-force auth")
    ]

    for i, (amt, status, narr) in enumerate(attempts):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_tx = t_start + timedelta(minutes=i * 3)

        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=t_tx.isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name="Global FastPay Automated Gateway",
            counterparty_country="US",
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            reference_narrative=narr,
            device_id="DEV-BOTNET-CLUSTER-X7",
            ip_address="198.51.100.44",
            ip_country="NL",
            is_card_present=False,
            card_entry_mode="CNP_ECOMMERCE",
            auth_status=status,
            is_fraud_synthetic=True,
            fraud_typology_tag="BIN_ATTACK_VELOCITY"
        ))

    return txs

def inject_bec_impersonation_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-09: Business Email Compromise (BEC) & Executive Impersonation.
    High-value wire diversion spoofing executive authority for confidential acquisition.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_tx = anchor_date.replace(hour=10, minute=45)

    wire_amt = round(random.uniform(35000.0, 75000.0), 2)
    tx_id = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1

    txs.append(Transaction(
        transaction_id=tx_id,
        customer_id=customer.customer_id,
        timestamp=t_tx.isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=wire_amt,
        counterparty_name="Meridian Global Acquisitions Nominee Ltd",
        counterparty_country="HK",
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Strictly Confidential M&A Acquisition Settlement Ref #9941 / CEO Authorization Required",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        is_new_payee=True,
        payee_first_seen_hours=0.1,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="BEC_PAYROLL_IMPERSONATION"
    ))

    return txs

def inject_aitm_session_hijack_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-10: Adversary-in-the-Middle (AitM) Phishing Session Hijack.
    Stolen session token replayed from hosting/VPN proxy to drain funds without credential reset.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_start = anchor_date.replace(hour=16, minute=10)

    # 1. Legitimate user session
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=t_start.isoformat(),
        transaction_type=TransactionType.ONLINE_PURCHASE,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=32.40,
        counterparty_name="City Transit Authority",
        counterparty_country=customer.residence_country,
        counterparty_category="RETAILER",
        channel="WEB_PORTAL",
        reference_narrative="Commuter travel card reload",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=False
    ))

    # 2. Hostile session token replay drain 25 minutes later
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    drain_amt = round(random.uniform(5400.0, 11500.0), 2)
    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=(t_start + timedelta(minutes=25)).isoformat(),
        transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=drain_amt,
        counterparty_name="SwiftClear Virtual Settlement Hub",
        counterparty_country="US",
        counterparty_category="CRYPTO_EXCHANGE",
        channel="WEB_PORTAL",
        reference_narrative="Reverse proxy session token replay: Instant wire out to third-party clearing wallet",
        device_id=customer.device_primary_id, # User-agent/device header cloned
        ip_address="185.191.171.12",          # Hostile VPN / proxy IP
        ip_country="DE",
        is_new_payee=True,
        payee_first_seen_hours=0.2,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="PHISHING_AITM_SESSION_HIJACK"
    ))

    return txs

def inject_overpayment_scam_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    Fraud Typology FR-11: Counterfeit Overpayment & Fake Refund Scam.
    Victim receives fake check/ACH deposit, tricked into wiring back the excess before it bounces.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start
    t_in = anchor_date.replace(hour=9, minute=30)

    # 1. Fake check / ACH deposit
    deposit_amt = 16800.0
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=t_in.isoformat(),
        transaction_type=TransactionType.ACH_DEPOSIT,
        direction=TransactionDirection.INBOUND,
        amount_usd=deposit_amt,
        counterparty_name="National Corporate Disbursing Escrow",
        counterparty_country=customer.residence_country,
        counterparty_category="INDIVIDUAL",
        channel="WEB_PORTAL",
        reference_narrative="Executive recruitment stipend & equipment advance check",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="REFUND_OVERPAYMENT_SCAM"
    ))

    # 2. Urgent refund wire 16 hours later before clearing
    refund_amt = 12400.0
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=(t_in + timedelta(hours=16)).isoformat(),
        transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=refund_amt,
        counterparty_name="Apex Logistics Logistics Agent",
        counterparty_country=customer.residence_country,
        counterparty_category="INDIVIDUAL",
        channel="WEB_PORTAL",
        reference_narrative="Overpayment refund of unused equipment advance to regional courier agent",
        device_id=customer.device_primary_id,
        ip_address=customer.primary_ip_address,
        ip_country=customer.primary_ip_country,
        is_new_payee=True,
        payee_first_seen_hours=0.5,
        auth_status="AUTHORIZED",
        is_fraud_synthetic=True,
        fraud_typology_tag="REFUND_OVERPAYMENT_SCAM"
    ))

    return txs

# ==========================================
# ADDITIONAL AML TYPOLOGY INJECTORS
# ==========================================

def inject_tbml_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-08: Trade-Based Money Laundering (TBML) & Over/Under-Invoicing.
    High-value cross-border wires referencing commercial freight invoices & shipping consignments.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # Inbound trade payment
    in_amt = round(random.uniform(55000.0, 95000.0), 2)
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=anchor_date.replace(hour=11, minute=15).isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_IN,
        direction=TransactionDirection.INBOUND,
        amount_usd=in_amt,
        counterparty_name="Al-Noor Petrochem & General Trading LLC",
        counterparty_country="AE",
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Consignment commercial invoice #4902 - raw industrial polymers cargo",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="TBML_OVER_INVOICING"
    ))

    # Outbound trade payment to offshore transit company 3 days later
    out_amt = round(in_amt * 0.88, 2)
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=(anchor_date + timedelta(days=3, hours=4)).isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=out_amt,
        counterparty_name="Star Ocean Shipping Logistics Ltd",
        counterparty_country="HK",
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Bill of Lading #BOL-9912 - bulk freight customs & transshipment fee",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="TBML_OVER_INVOICING"
    ))

    return txs

def inject_fan_out_layering_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-09: Fan-Out Layering / High-Velocity Fund Distribution.
    Large single inbound credit fragmented into multiple small outbound transfers across beneficiaries.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # 1. Large inbound credit
    total_in = 36000.0
    tx_id_in = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_in,
        customer_id=customer.customer_id,
        timestamp=anchor_date.replace(hour=8, minute=30).isoformat(),
        transaction_type=TransactionType.DOMESTIC_WIRE_IN,
        direction=TransactionDirection.INBOUND,
        amount_usd=total_in,
        counterparty_name="Vanguard Escrow Holdings Trust",
        counterparty_country=customer.residence_country,
        counterparty_category="OFFSHORE_CORP",
        channel="WEB_PORTAL",
        reference_narrative="Private contract disbursement proceeds",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="FAN_OUT_LAYERING"
    ))

    # 2. 5 rapid fan-out outbound transfers over next 24 hours
    split_payees = [
        ("Alice Chen P2P Account", TransactionType.P2P_TRANSFER_OUT, 6800.0, "PEER"),
        ("David Rossi Remittance Link", TransactionType.P2P_TRANSFER_OUT, 7200.0, "PEER"),
        ("Kraken Digital Ramp", TransactionType.CRYPTO_PURCHASE, 6500.0, "CRYPTO_EXCHANGE"),
        ("QuickPay Prepaid Settlement", TransactionType.DOMESTIC_WIRE_OUT, 7000.0, "OFFSHORE_CORP"),
        ("Apex Intermediary Partner", TransactionType.DOMESTIC_WIRE_OUT, 6900.0, "INDIVIDUAL")
    ]

    for i, (payee, tx_type, amt, cat) in enumerate(split_payees):
        tx_id_out = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_out = anchor_date + timedelta(hours=i * 4 + 2)

        txs.append(Transaction(
            transaction_id=tx_id_out,
            customer_id=customer.customer_id,
            timestamp=t_out.isoformat(),
            transaction_type=tx_type,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=amt,
            counterparty_name=payee,
            counterparty_country=customer.residence_country,
            counterparty_category=cat,
            channel="MOBILE_APP",
            reference_narrative=f"Fan-out distribution leg #{i+1} settlement",
            is_new_payee=True,
            is_suspicious_synthetic=True,
            synthetic_typology_tag="FAN_OUT_LAYERING"
        ))

    return txs

def inject_cuckoo_smurfing_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-10: Cuckoo Smurfing & Hawala Third-Party Remittance Matching.
    Multiple unrelated third parties deposit cash or local transfers into account to fulfill Hawala order.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    deposits = [
        ("Branch Cash Deposit Counter #12", "ATM_BRANCH", 4800.0),
        ("Sarah Jenkins Domestic Transfer", "INDIVIDUAL", 4200.0),
        ("Metro Retail Cash Counter", "ATM_BRANCH", 4600.0),
        ("Liam O'Connor P2P Credit", "PEER", 4900.0)
    ]

    for i, (cp_name, cat, amt) in enumerate(deposits):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        t_tx = anchor_date + timedelta(days=i * 2 + 1, hours=12, minutes=random.randint(10, 50))

        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=t_tx.isoformat(),
            transaction_type=TransactionType.CASH_DEPOSIT if cat == "ATM_BRANCH" else TransactionType.DOMESTIC_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=amt,
            counterparty_name=cp_name,
            counterparty_country=customer.residence_country,
            counterparty_category=cat,
            channel="BRANCH_TELLER" if cat == "ATM_BRANCH" else "ACH",
            reference_narrative="Hawala third-party remittance aggregation deposit",
            is_suspicious_synthetic=True,
            synthetic_typology_tag="CUCKOO_SMURFING"
        ))

    return txs

def inject_crypto_mixer_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-11: Crypto Mixer, Tumbler & Anonymity Protocol Interaction.
    Outbound and inbound transactions directly touching sanctioned mixers (Tornado Cash / Sinbad).
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # 1. Outbound to mixer
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=anchor_date.replace(hour=14, minute=20).isoformat(),
        transaction_type=TransactionType.CRYPTO_PURCHASE,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=18500.0,
        counterparty_name="Tornado Cash Router 0xd90e... (Sanctioned Protocol)",
        counterparty_country="SC",
        counterparty_category="CRYPTO_MIXER",
        channel="WEB_PORTAL",
        reference_narrative="Direct deposit to zero-knowledge privacy pool / mixer contract",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="CRYPTO_MIXER_HOP"
    ))

    # 2. Obfuscated return hop 48 hours later
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=(anchor_date + timedelta(days=2, hours=3)).isoformat(),
        transaction_type=TransactionType.CRYPTO_CASHOUT,
        direction=TransactionDirection.INBOUND,
        amount_usd=17800.0,
        counterparty_name="Wasabi CoinJoin Anonymized Aggregator",
        counterparty_country="VG",
        counterparty_category="CRYPTO_MIXER",
        channel="WEB_PORTAL",
        reference_narrative="Cleaned crypto cash-out hop from privacy tumbler pool",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="CRYPTO_MIXER_HOP"
    ))

    return txs

def inject_human_trafficking_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-12: Human Trafficking & Labor Exploitation Red Flags.
    Centralized wage pooling from vulnerable workers followed by immediate late-night ATM cash drain.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # Centralized worker deposits
    workers = ["Worker Wage Credit 01", "Worker Wage Credit 02", "Worker Wage Credit 03"]
    for i, w in enumerate(workers):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=(anchor_date + timedelta(hours=i * 2 + 8)).isoformat(),
            transaction_type=TransactionType.P2P_TRANSFER_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=850.0,
            counterparty_name=w,
            counterparty_country=customer.residence_country,
            counterparty_category="PEER",
            channel="MOBILE_APP",
            reference_narrative="Worker wage deduction for recruitment fee / centralized payroll skimming",
            is_suspicious_synthetic=True,
            synthetic_typology_tag="HUMAN_TRAFFICKING_RED_FLAGS"
        ))

    # Late night cash withdrawals in transit corridor
    for j in range(3):
        tx_id = f"TXN-{current_tx_id:07d}"
        current_tx_id += 1
        txs.append(Transaction(
            transaction_id=tx_id,
            customer_id=customer.customer_id,
            timestamp=(anchor_date + timedelta(days=1, hours=2, minutes=j * 15 + 10)).isoformat(),
            transaction_type=TransactionType.ATM_WITHDRAWAL,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=800.0,
            counterparty_name="Highway Border Travel Plaza ATM",
            counterparty_country=customer.residence_country,
            counterparty_category="ATM",
            channel="ATM",
            reference_narrative="Late-night ATM cash extraction / centralized wage pooling cashout",
            is_suspicious_synthetic=True,
            synthetic_typology_tag="HUMAN_TRAFFICKING_RED_FLAGS"
        ))

    return txs

def inject_loan_wash_scenario(
    customer: CustomerProfile,
    anchor_date: datetime,
    tx_counter_start: int
) -> List[Transaction]:
    """
    AML Typology TM-13: Loan Collateral Laundering & Rapid Early Liquidation.
    Customer secures loan disbursement and liquidates the debt within days using unverified third-party funds.
    """
    txs: List[Transaction] = []
    current_tx_id = tx_counter_start

    # Loan disbursement
    tx_id_1 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_1,
        customer_id=customer.customer_id,
        timestamp=anchor_date.replace(hour=10, minute=0).isoformat(),
        transaction_type=TransactionType.DOMESTIC_WIRE_IN,
        direction=TransactionDirection.INBOUND,
        amount_usd=40000.0,
        counterparty_name="Valiant Commercial Credit Disbursal Unit",
        counterparty_country=customer.residence_country,
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Term loan disbursement principal funding",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="LOAN_COLLATERAL_WASH"
    ))

    # Rapid early payoff 10 days later with offshore funds
    tx_id_2 = f"TXN-{current_tx_id:07d}"
    current_tx_id += 1
    txs.append(Transaction(
        transaction_id=tx_id_2,
        customer_id=customer.customer_id,
        timestamp=(anchor_date + timedelta(days=10, hours=5)).isoformat(),
        transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
        direction=TransactionDirection.OUTBOUND,
        amount_usd=40150.0,
        counterparty_name="Valiant Credit Loan Servicing Dept",
        counterparty_country=customer.residence_country,
        counterparty_category="OFFSHORE_CORP",
        channel="SWIFT",
        reference_narrative="Loan settlement full: Early payoff using offshore liquidity release",
        is_suspicious_synthetic=True,
        synthetic_typology_tag="LOAN_COLLATERAL_WASH"
    ))

    return txs
