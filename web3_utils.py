"""
web3_utils.py
-------------
Reads utilization rate directly from lending protocol contracts on Arbitrum.

Supported:
- Aave v3:     AaveProtocolDataProvider.getReserveData()
- Compound v3: Comet.getUtilization()

For all other protocols, callers should use DefiLlama data or mark as N/A.
"""

from web3 import Web3

ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"


# ── Aave v3 ───────────────────────────────────────────────────────────────────

AAVE_DATA_PROVIDER = "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654"

AAVE_TOKENS = {
    "USDC":   "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "USDT":   "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "DAI":    "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
}

AAVE_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {"internalType": "uint256", "name": "unbacked",                "type": "uint256"},
            {"internalType": "uint256", "name": "accruedToTreasuryScaled", "type": "uint256"},
            {"internalType": "uint256", "name": "totalAToken",             "type": "uint256"},
            {"internalType": "uint256", "name": "totalStableDebt",         "type": "uint256"},
            {"internalType": "uint256", "name": "totalVariableDebt",       "type": "uint256"},
            {"internalType": "uint256", "name": "liquidityRate",           "type": "uint256"},
            {"internalType": "uint256", "name": "variableBorrowRate",      "type": "uint256"},
            {"internalType": "uint256", "name": "stableBorrowRate",        "type": "uint256"},
            {"internalType": "uint256", "name": "averageStableBorrowRate", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidityIndex",          "type": "uint256"},
            {"internalType": "uint256", "name": "variableBorrowIndex",     "type": "uint256"},
            {"internalType": "uint256", "name": "lastUpdateTimestamp",     "type": "uint40"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


# ── Compound v3 ───────────────────────────────────────────────────────────────

# Each Compound v3 market is a separate Comet contract.
# getUtilization() returns a value scaled to 1e18 (1e18 = 100%).
COMPOUND_COMETS = {
    "USDC": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
    "USDT": "0xd98Be00b5D27fc98112BdE293e487f8D4cA57d07",
}

COMET_ABI = [
    {
        "inputs": [],
        "name": "getUtilization",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _w3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to Arbitrum RPC: {ARBITRUM_RPC}")
    return w3


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 6)


# ── Aave v3 ───────────────────────────────────────────────────────────────────

def _aave_utilization(symbol: str) -> float | None:
    if symbol not in AAVE_TOKENS:
        return None
    try:
        w3       = _w3()
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(AAVE_DATA_PROVIDER),
            abi=AAVE_ABI,
        )
        data         = contract.functions.getReserveData(
            Web3.to_checksum_address(AAVE_TOKENS[symbol])
        ).call()
        total_atoken = data[2]
        total_debt   = data[3] + data[4]
        if total_atoken == 0:
            return 0.0
        return _clamp(total_debt / total_atoken)
    except Exception as e:
        print(f"  [web3/aave] {symbol}: {e}")
        return None


# ── Compound v3 ───────────────────────────────────────────────────────────────

def _compound_utilization(symbol: str) -> float | None:
    if symbol not in COMPOUND_COMETS:
        return None
    try:
        w3       = _w3()
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(COMPOUND_COMETS[symbol]),
            abi=COMET_ABI,
        )
        return _clamp(contract.functions.getUtilization().call() / 1e18)
    except Exception as e:
        print(f"  [web3/compound] {symbol}: {e}")
        return None


# ── Public interface ──────────────────────────────────────────────────────────

def get_all_utilization_rates() -> dict[str, dict[str, float | None]]:
    """
    Return on-chain utilization rates for all supported protocols.

    Output: { protocol_name: { symbol: rate } }

    Example:
        {
            "aave-v3":     { "USDC": 0.606, "USDT": 0.628, "DAI": 0.635, "USDC.e": 0.558 },
            "compound-v3": { "USDC": 0.612, "USDT": 0.631 }
        }
    """
    results = {}

    print("  [web3] Reading Aave v3 utilization rates...")
    aave = {}
    for symbol in AAVE_TOKENS:
        rate = _aave_utilization(symbol)
        aave[symbol] = rate
        print(f"    {symbol:<8} {f'{rate*100:.2f}%' if rate is not None else 'N/A'}")
    results["aave-v3"] = aave

    print("  [web3] Reading Compound v3 utilization rates...")
    compound = {}
    for symbol in COMPOUND_COMETS:
        rate = _compound_utilization(symbol)
        compound[symbol] = rate
        print(f"    {symbol:<8} {f'{rate*100:.2f}%' if rate is not None else 'N/A'}")
    results["compound-v3"] = compound

    return results


if __name__ == "__main__":
    rates = get_all_utilization_rates()
    print("\nSummary:")
    for protocol, tokens in rates.items():
        for symbol, rate in tokens.items():
            print(f"  {protocol:<15} {symbol:<8} {f'{rate*100:.2f}%' if rate is not None else 'N/A'}")
