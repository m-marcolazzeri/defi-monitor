"""
Web3 Utilities — Aave v3 On-Chain Data Reader
-----------------------------------------------
Legge l'utilization rate direttamente dal contratto Aave v3 su Arbitrum.

Perché serve questo file:
  DefiLlama non restituisce l'utilization rate per tutti i pool.
  Questo modulo lo calcola direttamente dalla blockchain, senza intermediari.

Formula:
  utilization_rate = total_debt / (total_debt + available_liquidity)

Contratti usati:
  - AaveProtocolDataProvider: aggrega i dati di tutte le reserve Aave
    Indirizzo Arbitrum: 0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654

Token supportati (Arbitrum):
  - USDC:   0xaf88d065e77c8cC2239327C5EDb3A432268e5831
  - USDT:   0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9
  - DAI:    0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1
  - USDC.e: 0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8
"""

from web3 import Web3

# ─── Configurazione ───────────────────────────────────────────────────────────

# RPC pubblico Arbitrum — nessuna API key necessaria
# Se dovesse essere instabile, sostituisci con un URL Alchemy gratuito
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"

# AaveProtocolDataProvider — contratto che espone i dati aggregati di Aave v3
DATA_PROVIDER_ADDRESS = "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654"

# Indirizzi token su Arbitrum
TOKEN_ADDRESSES = {
    "USDC":   "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "USDT":   "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "DAI":    "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
}

# ABI minimo del DataProvider — solo la funzione che ci serve
# getReserveData restituisce: availableLiquidity, totalStableDebt,
# totalVariableDebt, liquidityRate, variableBorrowRate, ...
DATA_PROVIDER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {"internalType": "uint256", "name": "unbacked",                  "type": "uint256"},
            {"internalType": "uint256", "name": "accruedToTreasuryScaled",   "type": "uint256"},
            {"internalType": "uint256", "name": "totalAToken",               "type": "uint256"},
            {"internalType": "uint256", "name": "totalStableDebt",           "type": "uint256"},
            {"internalType": "uint256", "name": "totalVariableDebt",         "type": "uint256"},
            {"internalType": "uint256", "name": "liquidityRate",             "type": "uint256"},
            {"internalType": "uint256", "name": "variableBorrowRate",        "type": "uint256"},
            {"internalType": "uint256", "name": "stableBorrowRate",          "type": "uint256"},
            {"internalType": "uint256", "name": "averageStableBorrowRate",   "type": "uint256"},
            {"internalType": "uint256", "name": "liquidityIndex",            "type": "uint256"},
            {"internalType": "uint256", "name": "variableBorrowIndex",       "type": "uint256"},
            {"internalType": "uint256", "name": "lastUpdateTimestamp",       "type": "uint40"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


# ─── Connessione ──────────────────────────────────────────────────────────────

def get_web3() -> Web3:
    """Crea e restituisce una connessione Web3 ad Arbitrum."""
    w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
    if not w3.is_connected():
        raise ConnectionError(
            "Impossibile connettersi ad Arbitrum.\n"
            "Controlla la connessione internet oppure sostituisci ARBITRUM_RPC "
            "con un URL Alchemy gratuito da https://alchemy.com"
        )
    return w3


def get_data_provider(w3: Web3):
    """Restituisce l'istanza del contratto AaveProtocolDataProvider."""
    address = Web3.to_checksum_address(DATA_PROVIDER_ADDRESS)
    return w3.eth.contract(address=address, abi=DATA_PROVIDER_ABI)


# ─── Lettura dati ─────────────────────────────────────────────────────────────

def get_utilization_rate(symbol: str) -> float | None:
    """
    Calcola l'utilization rate di un token su Aave v3 Arbitrum.

    Formula:
        utilization = total_debt / (total_debt + available_liquidity)

    Dove:
        total_debt        = totalStableDebt + totalVariableDebt
        available_liquidity = totalAToken - total_debt

    Restituisce un float tra 0 e 1, oppure None in caso di errore.

    Esempio:
        >>> get_utilization_rate("USDC")
        0.7823   # 78.23% della liquidità è stata presa in prestito
    """
    if symbol not in TOKEN_ADDRESSES:
        return None

    try:
        w3 = get_web3()
        contract = get_data_provider(w3)
        token_address = Web3.to_checksum_address(TOKEN_ADDRESSES[symbol])

        # Chiama il contratto — operazione di sola lettura, non costa gas
        data = contract.functions.getReserveData(token_address).call()

        total_a_token      = data[2]   # totalAToken (totale depositato)
        total_stable_debt  = data[3]   # totalStableDebt
        total_variable_debt = data[4]  # totalVariableDebt

        total_debt = total_stable_debt + total_variable_debt

        if total_a_token == 0:
            return 0.0

        utilization = total_debt / total_a_token
        # Clamp tra 0 e 1 per sicurezza numerica
        return round(min(max(utilization, 0.0), 1.0), 6)

    except ConnectionError as e:
        print(f"  ⚠️  Web3 connection error per {symbol}: {e}")
        return None
    except Exception as e:
        print(f"  ⚠️  Errore lettura on-chain per {symbol}: {e}")
        return None


def get_all_utilization_rates() -> dict[str, float | None]:
    """
    Restituisce l'utilization rate per tutti i token supportati.

    Esempio output:
        {
            "USDC":   0.7823,
            "USDT":   0.6541,
            "DAI":    0.4210,
            "USDC.e": 0.3891
        }
    """
    print("  → Lettura utilization rate on-chain da Aave v3...")
    results = {}
    for symbol in TOKEN_ADDRESSES:
        rate = get_utilization_rate(symbol)
        results[symbol] = rate
        if rate is not None:
            print(f"    {symbol:8s}: {rate*100:.2f}%")
        else:
            print(f"    {symbol:8s}: N/A")
    return results


# ─── Test standalone ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nTest Web3 — Aave v3 Arbitrum Utilization Rates")
    print("="*50)
    rates = get_all_utilization_rates()
    print("="*50)
    print("\nTest completato.")
