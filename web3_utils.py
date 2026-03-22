"""
web3_utils.py
-------------
Reads utilization rate directly from the Aave v3 contract on Arbitrum.

DefiLlama does not reliably populate the utilization field for all pools.
This module computes it from on-chain data using the AaveProtocolDataProvider.

Formula: utilization = total_debt / total_atoken
  where total_debt = totalStableDebt + totalVariableDebt
"""

from web3 import Web3

ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"

# AaveProtocolDataProvider — Arbitrum
DATA_PROVIDER_ADDRESS = "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654"

TOKEN_ADDRESSES = {
    "USDC":   "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "USDT":   "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "DAI":    "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
}

# Minimal ABI — only getReserveData is needed
DATA_PROVIDER_ABI = [
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


def _get_contract():
    w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to Arbitrum RPC: {ARBITRUM_RPC}")
    address = Web3.to_checksum_address(DATA_PROVIDER_ADDRESS)
    return w3.eth.contract(address=address, abi=DATA_PROVIDER_ABI)


def get_utilization_rate(symbol: str) -> float | None:
    """Return utilization rate for a token on Aave v3 Arbitrum, or None on failure."""
    if symbol not in TOKEN_ADDRESSES:
        return None
    try:
        contract = _get_contract()
        token = Web3.to_checksum_address(TOKEN_ADDRESSES[symbol])
        data = contract.functions.getReserveData(token).call()

        total_atoken = data[2]
        total_debt   = data[3] + data[4]  # stableDebt + variableDebt

        if total_atoken == 0:
            return 0.0

        return round(min(max(total_debt / total_atoken, 0.0), 1.0), 6)

    except Exception as e:
        print(f"  [web3] {symbol}: {e}")
        return None


def get_all_utilization_rates() -> dict[str, float | None]:
    """Return utilization rates for all supported tokens."""
    print("  [web3] Reading utilization rates from Aave v3 on-chain...")
    results = {}
    for symbol in TOKEN_ADDRESSES:
        rate = get_utilization_rate(symbol)
        results[symbol] = rate
        status = f"{rate*100:.2f}%" if rate is not None else "N/A"
        print(f"    {symbol:<8} {status}")
    return results


if __name__ == "__main__":
    get_all_utilization_rates()
